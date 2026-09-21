# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import json

# Django imports
from django.utils import timezone
from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Subquery, OuterRef
from django.db.models.functions import Coalesce
from django.utils.decorators import method_decorator
from django.views.decorators.gzip import gzip_page

# Third Party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import allow_permission, ROLE
from plane.app.serializers import (
    IssueCreateSerializer,
    DraftIssueCreateSerializer,
    DraftIssueSerializer,
    DraftIssueDetailSerializer,
)
from plane.db.models import (
    Issue,
    DraftIssue,
    DraftIssueAssignee,
    DraftIssueLabel,
    DraftIssueModule,
    CycleIssue,
    ModuleIssue,
    DraftIssueCycle,
    Workspace,
    FileAsset,
)
from .. import BaseViewSet
from plane.bgtasks.issue_activities_task import issue_activity
from plane.utils.issue_filters import issue_filters
from plane.utils.host import base_host
from plane.utils.sqlite_aggregates import JsonGroupUuidArray, empty_json_array


class WorkspaceDraftIssueViewSet(BaseViewSet):
    model = DraftIssue

    def get_queryset(self):
        return (
            DraftIssue.objects.filter(workspace__slug=self.kwargs.get("slug"))
            .select_related("workspace", "project", "state", "parent")
            .prefetch_related("assignees", "labels", "draft_issue_module__module")
            .annotate(
                cycle_id=Subquery(
                    DraftIssueCycle.objects.filter(draft_issue=OuterRef("id"), deleted_at__isnull=True).values(
                        "cycle_id"
                    )[:1]
                )
            )
            .annotate(
                label_ids=Coalesce(
                    Subquery(
                        DraftIssueLabel.objects.filter(
                            draft_issue_id=OuterRef("pk"),
                            deleted_at__isnull=True,
                            label_id__isnull=False,
                        )
                        .values("draft_issue_id")
                        .annotate(arr=JsonGroupUuidArray("label_id"))
                        .values("arr")
                    ),
                    empty_json_array(),
                ),
                assignee_ids=Coalesce(
                    Subquery(
                        DraftIssueAssignee.objects.filter(
                            draft_issue_id=OuterRef("pk"),
                            deleted_at__isnull=True,
                            assignee_id__isnull=False,
                            assignee__member_project__is_active=True,
                        )
                        .values("draft_issue_id")
                        .annotate(arr=JsonGroupUuidArray("assignee_id"))
                        .values("arr")
                    ),
                    empty_json_array(),
                ),
                module_ids=Coalesce(
                    Subquery(
                        DraftIssueModule.objects.filter(
                            draft_issue_id=OuterRef("pk"),
                            deleted_at__isnull=True,
                            module_id__isnull=False,
                            module__archived_at__isnull=True,
                        )
                        .values("draft_issue_id")
                        .annotate(arr=JsonGroupUuidArray("module_id"))
                        .values("arr")
                    ),
                    empty_json_array(),
                ),
            )
        ).distinct()

    @method_decorator(gzip_page)
    @allow_permission(allowed_roles=[ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def list(self, request, slug):
        filters = issue_filters(request.query_params, "GET")
        issues = self.get_queryset().filter(created_by=request.user).order_by("-created_at")

        issues = issues.filter(**filters)
        # List Paginate
        return self.paginate(
            request=request,
            queryset=(issues),
            on_results=lambda issues: DraftIssueSerializer(issues, many=True).data,
        )

    @allow_permission(allowed_roles=[ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def create(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)

        serializer = DraftIssueCreateSerializer(
            data=request.data,
            context={
                "workspace_id": workspace.id,
                "project_id": request.data.get("project_id", None),
            },
        )
        if serializer.is_valid():
            serializer.save()
            issue = (
                self.get_queryset()
                .filter(pk=serializer.data.get("id"))
                .values(
                    "id",
                    "name",
                    "state_id",
                    "sort_order",
                    "completed_at",
                    "estimate_point",
                    "priority",
                    "start_date",
                    "target_date",
                    "project_id",
                    "parent_id",
                    "cycle_id",
                    "module_ids",
                    "label_ids",
                    "assignee_ids",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "updated_by",
                    "type_id",
                    "description_html",
                )
                .first()
            )

            return Response(issue, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission(
        allowed_roles=[ROLE.ADMIN, ROLE.MEMBER],
        creator=True,
        model=Issue,
        level="WORKSPACE",
    )
    def partial_update(self, request, slug, pk):
        issue = self.get_queryset().filter(pk=pk, created_by=request.user).first()

        if not issue:
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)

        project_id = request.data.get("project_id", issue.project_id)

        serializer = DraftIssueCreateSerializer(
            issue,
            data=request.data,
            partial=True,
            context={
                "project_id": project_id,
                "cycle_id": request.data.get("cycle_id", "not_provided"),
            },
        )

        if serializer.is_valid():
            serializer.save()

            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission(allowed_roles=[ROLE.ADMIN], creator=True, model=Issue, level="WORKSPACE")
    def retrieve(self, request, slug, pk=None):
        issue = self.get_queryset().filter(pk=pk, created_by=request.user).first()

        if not issue:
            return Response(
                {"error": "The required object does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = DraftIssueDetailSerializer(issue)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission(allowed_roles=[ROLE.ADMIN], creator=True, model=DraftIssue, level="WORKSPACE")
    def destroy(self, request, slug, pk=None):
        draft_issue = DraftIssue.objects.get(workspace__slug=slug, pk=pk)
        draft_issue.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @allow_permission(allowed_roles=[ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def create_draft_to_issue(self, request, slug, draft_id):
        draft_issue = self.get_queryset().filter(pk=draft_id).first()

        if not draft_issue.project_id:
            return Response(
                {"error": "Project is required to create an issue."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = IssueCreateSerializer(
            data=request.data,
            context={
                "project_id": draft_issue.project_id,
                "workspace_id": draft_issue.project.workspace_id,
                "default_assignee_id": draft_issue.project.default_assignee_id,
            },
        )

        if serializer.is_valid():
            serializer.save()

            issue_activity.delay(
                type="issue.activity.created",
                requested_data=json.dumps(self.request.data, cls=DjangoJSONEncoder),
                actor_id=str(request.user.id),
                issue_id=str(serializer.data.get("id", None)),
                project_id=str(draft_issue.project_id),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
                notification=True,
                origin=base_host(request=request, is_app=True),
            )

            if request.data.get("cycle_id", None):
                created_records = CycleIssue.objects.create(
                    cycle_id=request.data.get("cycle_id", None),
                    issue_id=serializer.data.get("id", None),
                    project_id=draft_issue.project_id,
                    workspace_id=draft_issue.workspace_id,
                    created_by_id=draft_issue.created_by_id,
                    updated_by_id=draft_issue.updated_by_id,
                )
                # Capture Issue Activity
                issue_activity.delay(
                    type="cycle.activity.created",
                    requested_data=None,
                    actor_id=str(self.request.user.id),
                    issue_id=None,
                    project_id=str(self.kwargs.get("project_id", None)),
                    current_instance=json.dumps(
                        {
                            "updated_cycle_issues": None,
                            "created_cycle_issues": serializers.serialize("json", [created_records]),
                        }
                    ),
                    epoch=int(timezone.now().timestamp()),
                    notification=True,
                    origin=base_host(request=request, is_app=True),
                )

            if request.data.get("module_ids", []):
                # bulk create the module
                ModuleIssue.objects.bulk_create(
                    [
                        ModuleIssue(
                            module_id=module,
                            issue_id=serializer.data.get("id", None),
                            workspace_id=draft_issue.workspace_id,
                            project_id=draft_issue.project_id,
                            created_by_id=draft_issue.created_by_id,
                            updated_by_id=draft_issue.updated_by_id,
                        )
                        for module in request.data.get("module_ids", [])
                    ],
                    batch_size=10,
                )
                # Update the activity
                _ = [
                    issue_activity.delay(
                        type="module.activity.created",
                        requested_data=json.dumps({"module_id": str(module)}),
                        actor_id=str(request.user.id),
                        issue_id=serializer.data.get("id", None),
                        project_id=draft_issue.project_id,
                        current_instance=None,
                        epoch=int(timezone.now().timestamp()),
                        notification=True,
                        origin=base_host(request=request, is_app=True),
                    )
                    for module in request.data.get("module_ids", [])
                ]

            # Update file assets
            file_assets = FileAsset.objects.filter(draft_issue_id=draft_id)
            file_assets.update(
                issue_id=serializer.data.get("id", None),
                entity_type=FileAsset.EntityTypeContext.ISSUE_DESCRIPTION,
                draft_issue_id=None,
            )

            # delete the draft issue
            draft_issue.delete()

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
