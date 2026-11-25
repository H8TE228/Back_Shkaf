from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from exchange_points.models import ExchangePoint
from items.exceptions import StateConflict

from .models import (
    InventoryRecord,
    PointAuditLog,
    PointMember,
    ShiftAssignment,
    VolunteerShift,
)
from .serializers import (
    AssignmentSerializer,
    InventorySerializer,
    PointRoleSerializer,
    PointStatusSerializer,
    ShiftSerializer,
)

ORGANIZER = PointMember.Role.ORGANIZER
VOLUNTEER = PointMember.Role.VOLUNTEER


def audit(point, actor, action, **data):
    PointAuditLog.objects.create(point=point, actor=actor, action=action, data=data)


class PointAccess:
    permission_classes = (permissions.IsAuthenticated,)
    allowed_roles = (ORGANIZER,)

    def get_point(self, *, lock=False):
        points = ExchangePoint.objects.all()
        if lock:
            points = points.select_for_update()
        point = get_object_or_404(points, pk=self.kwargs['point_id'])
        if not self.request.user.is_superuser and not point.members.filter(
            user=self.request.user, role__in=self.allowed_roles
        ).exists():
            raise PermissionDenied()
        return point


@extend_schema(tags=['organizer'])
class MyPointRolesView(generics.ListAPIView):
    serializer_class = PointRoleSerializer
    permission_classes = (permissions.IsAuthenticated,)
    queryset = PointMember.objects.none()

    def get_queryset(self):
        return PointMember.objects.filter(user=self.request.user).order_by('point_id')


@extend_schema(tags=['organizer'])
class PointStatusView(PointAccess, generics.GenericAPIView):
    serializer_class = PointStatusSerializer

    @transaction.atomic
    def patch(self, request, point_id):
        point = self.get_point(lock=True)
        previous = point.status
        serializer = self.get_serializer(point, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if previous != point.status:
            audit(point, request.user, 'point.status', before=previous, after=point.status)
        return Response(serializer.data)


@extend_schema(tags=['organizer'])
class InventoryView(PointAccess, generics.ListCreateAPIView):
    serializer_class = InventorySerializer
    queryset = InventoryRecord.objects.none()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return self.get_point().inventory_records.all()

    @transaction.atomic
    def perform_create(self, serializer):
        point = self.get_point(lock=True)
        data = serializer.validated_data
        item_type = data['item_type']
        if not point.item_types.filter(pk=item_type.pk).exists():
            raise ValidationError({'item_type': 'This item type is not handled by the point.'})
        if data['direction'] == InventoryRecord.Direction.ISSUE:
            totals = point.inventory_records.filter(item_type=item_type).aggregate(
                intake=Sum('quantity', filter=Q(direction=InventoryRecord.Direction.INTAKE), default=0),
                issue=Sum('quantity', filter=Q(direction=InventoryRecord.Direction.ISSUE), default=0),
            )
            if totals['intake'] - totals['issue'] < data['quantity']:
                raise StateConflict('Not enough items in stock.')
        record = serializer.save(point=point, recorded_by=self.request.user)
        audit(point, self.request.user, f'inventory.{record.direction}', record_id=record.pk,
              item_type_id=item_type.pk, quantity=record.quantity)


class ShiftQueryset(PointAccess):
    serializer_class = ShiftSerializer
    queryset = VolunteerShift.objects.none()

    def shifts(self, point):
        return point.volunteer_shifts.annotate(
            occupied=Count('assignments', filter=~Q(assignments__status=ShiftAssignment.Status.CANCELLED)),
            my_status=Subquery(ShiftAssignment.objects.filter(
                shift_id=OuterRef('pk'), user=self.request.user,
            ).values('status')[:1]),
        )

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return self.shifts(self.get_point())


def shift_times(shift):
    return {'starts_at': shift.starts_at.isoformat(), 'ends_at': shift.ends_at.isoformat(),
            'capacity': shift.capacity}


@extend_schema(tags=['organizer'])
class ShiftListView(ShiftQueryset, generics.ListCreateAPIView):
    @property
    def allowed_roles(self):
        return (ORGANIZER, VOLUNTEER) if self.request.method in permissions.SAFE_METHODS else (ORGANIZER,)

    @transaction.atomic
    def perform_create(self, serializer):
        point = self.get_point(lock=True)
        shift = serializer.save(point=point, created_by=self.request.user)
        shift.occupied = 0
        shift.my_status = None
        audit(point, self.request.user, 'shift.create', shift_id=shift.pk, after=shift_times(shift))


@extend_schema(tags=['organizer'])
class ShiftDetailView(ShiftQueryset, generics.RetrieveUpdateAPIView):
    lookup_url_kwarg = 'shift_id'
    http_method_names = ('get', 'patch', 'head', 'options')

    @property
    def allowed_roles(self):
        return (ORGANIZER, VOLUNTEER) if self.request.method in permissions.SAFE_METHODS else (ORGANIZER,)

    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        point = self.get_point(lock=True)
        shift = get_object_or_404(self.shifts(point), pk=self.kwargs['shift_id'])
        before = shift_times(shift)
        serializer = self.get_serializer(shift, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get('capacity', shift.capacity) < shift.occupied:
            raise StateConflict('Capacity cannot be lower than the number of participants.')
        serializer.save()
        if before != shift_times(shift):
            audit(point, request.user, 'shift.update', shift_id=shift.pk, before=before, after=shift_times(shift))
        return Response(serializer.data)


@extend_schema(tags=['organizer'])
class ShiftSignupView(PointAccess, generics.GenericAPIView):
    serializer_class = AssignmentSerializer
    allowed_roles = (VOLUNTEER,)

    @extend_schema(request=None, responses={200: AssignmentSerializer, 201: AssignmentSerializer})
    @transaction.atomic
    def post(self, request, point_id, shift_id):
        point = self.get_point(lock=True)
        shift = get_object_or_404(point.volunteer_shifts, pk=shift_id)
        assignments = shift.assignments
        assignment = assignments.filter(user=request.user).first()
        if assignment and assignment.status != ShiftAssignment.Status.CANCELLED:
            return Response(self.get_serializer(assignment).data)
        if shift.starts_at <= timezone.now():
            raise StateConflict('The shift has already started.')
        if assignments.exclude(status=ShiftAssignment.Status.CANCELLED).count() >= shift.capacity:
            raise StateConflict('The shift is full.')
        if assignment:
            assignment.status = ShiftAssignment.Status.SIGNED_UP
            assignment.save(update_fields=['status'])
        else:
            assignment = assignments.create(user=request.user)
        audit(point, request.user, 'shift.signup', shift_id=shift.pk, assignment_id=assignment.pk)
        return Response(self.get_serializer(assignment).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={204: None})
    @transaction.atomic
    def delete(self, request, point_id, shift_id):
        point = self.get_point(lock=True)
        shift = get_object_or_404(point.volunteer_shifts, pk=shift_id)
        assignment = shift.assignments.filter(user=request.user, status=ShiftAssignment.Status.SIGNED_UP).first()
        if assignment:
            if shift.starts_at <= timezone.now():
                raise StateConflict('The shift has already started.')
            assignment.status = ShiftAssignment.Status.CANCELLED
            assignment.save(update_fields=['status'])
            audit(point, request.user, 'shift.cancel', shift_id=shift.pk, assignment_id=assignment.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=['organizer'])
class ShiftAssignmentsView(PointAccess, generics.ListAPIView):
    serializer_class = AssignmentSerializer
    queryset = ShiftAssignment.objects.none()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        shift = get_object_or_404(self.get_point().volunteer_shifts, pk=self.kwargs['shift_id'])
        return shift.assignments.order_by('pk')


@extend_schema(tags=['organizer'])
class ShiftAttendanceView(PointAccess, generics.GenericAPIView):
    serializer_class = AssignmentSerializer

    @extend_schema(request=None)
    @transaction.atomic
    def post(self, request, point_id, shift_id, assignment_id):
        point = self.get_point(lock=True)
        shift = get_object_or_404(point.volunteer_shifts, pk=shift_id)
        assignment = get_object_or_404(shift.assignments, pk=assignment_id)
        if shift.starts_at > timezone.now() or assignment.status == ShiftAssignment.Status.CANCELLED:
            raise StateConflict('Attendance cannot be recorded for this assignment.')
        if assignment.status != ShiftAssignment.Status.ATTENDED:
            assignment.status = ShiftAssignment.Status.ATTENDED
            assignment.save(update_fields=['status'])
            audit(point, request.user, 'shift.attended', shift_id=shift.pk, assignment_id=assignment.pk)
        return Response(self.get_serializer(assignment).data)
