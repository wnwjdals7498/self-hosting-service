/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { Outlet } from "react-router";
import useSWR from "swr";
// components
import { LogoSpinner } from "@/components/common/logo-spinner";
import { PoweredBy } from "@/components/common/powered-by";
import { SomethingWentWrongError } from "@/components/issues/issue-layouts/error";
import { IssuesNavbarRoot } from "@/components/issues/navbar";
// hooks
import { PageNotFound } from "@/components/ui/not-found";
import { usePublish, usePublishList } from "@/hooks/store/publish";
import { useIssueFilter } from "@/hooks/store/use-issue-filter";
import type { Route } from "./+types/layout";

const DEFAULT_TITLE = "Plane";
const DEFAULT_DESCRIPTION = "Made with Plane, an AI-powered work management platform with publishing capabilities.";

// SPA build: no server loader runs, so OG/Twitter tags fall back to
// the static defaults. Per-anchor metadata is skipped since it would
// require SSR or a build-time prerender pass.
export function meta() {
  return [
    { title: DEFAULT_TITLE },
    { name: "description", content: DEFAULT_DESCRIPTION },
    { property: "og:title", content: DEFAULT_TITLE },
    { property: "og:description", content: DEFAULT_DESCRIPTION },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
    { name: "twitter:title", content: DEFAULT_TITLE },
    { name: "twitter:description", content: DEFAULT_DESCRIPTION },
  ];
}

function IssuesLayout(props: Route.ComponentProps) {
  const { anchor } = props.params;
  // store hooks
  const { fetchPublishSettings } = usePublishList();
  const publishSettings = usePublish(anchor);
  const { updateLayoutOptions } = useIssueFilter();
  // fetch publish settings
  const { error } = useSWR(
    anchor ? `PUBLISH_SETTINGS_${anchor}` : null,
    anchor
      ? async () => {
          const response = await fetchPublishSettings(anchor);
          if (response.view_props) {
            updateLayoutOptions({
              list: !!response.view_props.list,
              kanban: !!response.view_props.kanban,
              calendar: !!response.view_props.calendar,
              gantt: !!response.view_props.gantt,
              spreadsheet: !!response.view_props.spreadsheet,
            });
          }
        }
      : null
  );

  if (!publishSettings && !error) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-surface-1">
        <LogoSpinner />
      </div>
    );
  }

  if (error?.status === 404) return <PageNotFound />;

  if (error) return <SomethingWentWrongError />;

  return (
    <>
      <div className="relative flex h-screen min-h-[500px] w-screen flex-col overflow-hidden">
        <div className="relative flex h-[60px] shrink-0 items-center border-b border-subtle-1 bg-surface-1 select-none">
          <IssuesNavbarRoot publishSettings={publishSettings} />
        </div>
        <div className="relative size-full overflow-hidden bg-surface-2">
          <Outlet />
        </div>
      </div>
      <PoweredBy />
    </>
  );
}

export default observer(IssuesLayout);
