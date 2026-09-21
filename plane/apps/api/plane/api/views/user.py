# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import status
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiResponse

# Module imports
from plane.api.serializers import UserLiteSerializer
from plane.api.views.base import BaseAPIView
from plane.db.models import User
# fork-custom: include is_instance_admin so plane-mcp-server's admin_guard can
# gate admin-only tools from an X-Api-Key request (spec §5.3).
from plane.license.models import Instance, InstanceAdmin
from plane.utils.openapi.decorators import user_docs
from plane.utils.openapi import USER_EXAMPLE


class UserEndpoint(BaseAPIView):
    serializer_class = UserLiteSerializer
    model = User

    @user_docs(
        operation_id="get_current_user",
        summary="Get current user",
        description="Retrieve the authenticated user's profile information including basic details.",
        responses={
            200: OpenApiResponse(
                description="Current user profile",
                response=UserLiteSerializer,
                examples=[USER_EXAMPLE],
            ),
        },
    )
    def get(self, request):
        """Get current user

        Retrieve the authenticated user's profile information including basic details.
        Returns user data based on the current authentication context.
        """
        serializer = UserLiteSerializer(request.user)
        payload = dict(serializer.data)
        ## fork-custom
        instance = Instance.objects.first()
        payload["is_instance_admin"] = bool(
            instance is not None
            and InstanceAdmin.objects.filter(instance=instance, user=request.user).exists()
        )
        return Response(payload, status=status.HTTP_200_OK)
