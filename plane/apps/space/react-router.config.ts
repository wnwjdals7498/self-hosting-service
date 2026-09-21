import type { Config } from "@react-router/dev/config";
import { joinUrlPath } from "@plane/utils";

const basePath = joinUrlPath(process.env.VITE_SPACE_BASE_PATH ?? "", "/") ?? "/";

export default {
  appDirectory: "app",
  basename: basePath,
  // Space runs as a client-side app; build a static client bundle only
  // so Caddy can serve build/client/ directly at the /spaces/ prefix.
  ssr: false,
} satisfies Config;
