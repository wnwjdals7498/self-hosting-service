# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db.models import (
    Q,
    Value,
    F,
    Case,
    When,
    CharField,
    OuterRef,
    Subquery,
)
from django.db.models.functions import Coalesce, JSONObject, Concat
from django.db.models import QuerySet

from typing import List, Optional, Dict, Any, Union

# Module imports
from plane.db.models import (
    Cycle,
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueReaction,
    IssueVote,
    Label,
    Module,
    ModuleIssue,
    Project,
    ProjectMember,
    State,
    WorkspaceMember,
)
from plane.utils.sqlite_aggregates import JsonGroupArray, JsonGroupUuidArray, empty_json_array


def issue_queryset_grouper(
    queryset: QuerySet[Issue], group_by: Optional[str], sub_group_by: Optional[str]
) -> QuerySet[Issue]:
    FIELD_MAPPER = {
        "label_ids": "labels__id",
        "assignee_ids": "assignees__id",
        "module_ids": "issue_module__module_id",
    }

    GROUP_FILTER_MAPPER = {
        "assignees__id": Q(issue_assignee__deleted_at__isnull=True),
        "labels__id": Q(label_issue__deleted_at__isnull=True),
        "issue_module__module_id": Q(issue_module__deleted_at__isnull=True),
    }

    for group_key in [group_by, sub_group_by]:
        if group_key in GROUP_FILTER_MAPPER:
            queryset = queryset.filter(GROUP_FILTER_MAPPER[group_key])

    def _subq(key: str):
        if key == "assignee_ids":
            return Subquery(
                IssueAssignee.objects.filter(
                    issue_id=OuterRef("pk"),
                    deleted_at__isnull=True,
                    assignee_id__isnull=False,
                )
                .values("issue_id")
                .annotate(arr=JsonGroupUuidArray("assignee_id"))
                .values("arr")
            )
        if key == "label_ids":
            return Subquery(
                IssueLabel.objects.filter(
                    issue_id=OuterRef("pk"),
                    deleted_at__isnull=True,
                    label_id__isnull=False,
                )
                .values("issue_id")
                .annotate(arr=JsonGroupUuidArray("label_id"))
                .values("arr")
            )
        # module_ids
        return Subquery(
            ModuleIssue.objects.filter(
                issue_id=OuterRef("pk"),
                module_id__isnull=False,
            )
            .values("issue_id")
            .annotate(arr=JsonGroupUuidArray("module_id"))
            .values("arr")
        )

    default_annotations = {
        key: Coalesce(_subq(key), empty_json_array())
        for key in ("assignee_ids", "label_ids", "module_ids")
        if FIELD_MAPPER.get(key) != group_by or FIELD_MAPPER.get(key) != sub_group_by
    }

    return queryset.annotate(**default_annotations)


def issue_on_results(
    issues: QuerySet[Issue], group_by: Optional[str], sub_group_by: Optional[str]
) -> List[Dict[str, Any]]:
    FIELD_MAPPER = {
        "labels__id": "label_ids",
        "assignees__id": "assignee_ids",
        "issue_module__module_id": "module_ids",
    }

    original_list = ["assignee_ids", "label_ids", "module_ids"]

    required_fields = [
        "id",
        "name",
        "state_id",
        "sort_order",
        "estimate_point",
        "priority",
        "start_date",
        "target_date",
        "sequence_id",
        "project_id",
        "parent_id",
        "cycle_id",
        "created_by",
        "state__group",
    ]

    if group_by in FIELD_MAPPER:
        original_list.remove(FIELD_MAPPER[group_by])
        original_list.append(group_by)

    if sub_group_by in FIELD_MAPPER:
        original_list.remove(FIELD_MAPPER[sub_group_by])
        original_list.append(sub_group_by)

    required_fields.extend(original_list)

    vote_items_subquery = Subquery(
        IssueVote.objects.filter(
            issue_id=OuterRef("pk"),
            deleted_at__isnull=True,
        )
        .values("issue_id")
        .annotate(
            arr=JsonGroupArray(
                JSONObject(
                    vote=F("vote"),
                    actor_details=JSONObject(
                        id=F("actor__id"),
                        first_name=F("actor__first_name"),
                        last_name=F("actor__last_name"),
                        avatar=F("actor__avatar"),
                        avatar_url=Case(
                            When(
                                actor__avatar_asset__isnull=False,
                                then=Concat(
                                    Value("/api/assets/v2/static/"),
                                    F("actor__avatar_asset"),
                                    Value("/"),
                                ),
                            ),
                            default=F("actor__avatar"),
                            output_field=CharField(),
                        ),
                        display_name=F("actor__display_name"),
                    ),
                )
            )
        )
        .values("arr")
    )

    reaction_items_subquery = Subquery(
        IssueReaction.objects.filter(
            issue_id=OuterRef("pk"),
            deleted_at__isnull=True,
        )
        .values("issue_id")
        .annotate(
            arr=JsonGroupArray(
                JSONObject(
                    reaction=F("reaction"),
                    actor_details=JSONObject(
                        id=F("actor__id"),
                        first_name=F("actor__first_name"),
                        last_name=F("actor__last_name"),
                        avatar=F("actor__avatar"),
                        avatar_url=Case(
                            When(
                                actor__avatar_asset__isnull=False,
                                then=Concat(
                                    Value("/api/assets/v2/static/"),
                                    F("actor__avatar_asset"),
                                    Value("/"),
                                ),
                            ),
                            default=F("actor__avatar"),
                            output_field=CharField(),
                        ),
                        display_name=F("actor__display_name"),
                    ),
                )
            )
        )
        .values("arr")
    )

    issues = issues.annotate(
        vote_items=Coalesce(vote_items_subquery, empty_json_array()),
        reaction_items=Coalesce(reaction_items_subquery, empty_json_array()),
    ).values(*required_fields, "vote_items", "reaction_items")

    return issues


def issue_group_values(
    field: str,
    slug: str,
    project_id: Optional[str] = None,
    filters: Dict[str, Any] = {},
    queryset: Optional[QuerySet] = None,
) -> List[Union[str, Any]]:
    if field == "state_id":
        queryset = State.objects.filter(is_triage=False, workspace__slug=slug).values_list("id", flat=True)
        if project_id:
            return list(queryset.filter(project_id=project_id))
        else:
            return list(queryset)
    if field == "labels__id":
        queryset = Label.objects.filter(workspace__slug=slug).values_list("id", flat=True)
        if project_id:
            return list(queryset.filter(project_id=project_id)) + ["None"]
        else:
            return list(queryset) + ["None"]
    if field == "assignees__id":
        if project_id:
            return ProjectMember.objects.filter(
                workspace__slug=slug, project_id=project_id, is_active=True
            ).values_list("member_id", flat=True)
        else:
            return list(
                WorkspaceMember.objects.filter(workspace__slug=slug, is_active=True).values_list("member_id", flat=True)
            )
    if field == "issue_module__module_id":
        queryset = Module.objects.filter(workspace__slug=slug).values_list("id", flat=True)
        if project_id:
            return list(queryset.filter(project_id=project_id)) + ["None"]
        else:
            return list(queryset) + ["None"]
    if field == "cycle_id":
        queryset = Cycle.objects.filter(workspace__slug=slug).values_list("id", flat=True)
        if project_id:
            return list(queryset.filter(project_id=project_id)) + ["None"]
        else:
            return list(queryset) + ["None"]
    if field == "project_id":
        queryset = Project.objects.filter(workspace__slug=slug).values_list("id", flat=True)
        return list(queryset)
    if field == "priority":
        return ["low", "medium", "high", "urgent", "none"]
    if field == "state__group":
        return ["backlog", "unstarted", "started", "completed", "cancelled"]
    if field == "target_date":
        queryset = queryset.values_list("target_date", flat=True).distinct()
        if project_id:
            return list(queryset.filter(project_id=project_id))
        else:
            return list(queryset)
    if field == "start_date":
        queryset = queryset.values_list("start_date", flat=True).distinct()
        if project_id:
            return list(queryset.filter(project_id=project_id))
        else:
            return list(queryset)

    if field == "created_by":
        queryset = queryset.values_list("created_by", flat=True).distinct()
        if project_id:
            return list(queryset.filter(project_id=project_id))
        else:
            return list(queryset)

    return []
