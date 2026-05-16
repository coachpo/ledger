import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { FINANCE_WORKSPACE_EXTENSION_KEY } from "@/extensions";
import { listExtensions, toggleExtension } from "@/lib/api/extensions";
import { queryKeys } from "@/lib/query-keys";
import type {
  ExtensionListRead,
  ExtensionRead,
  ExtensionToggleRequest,
} from "@/lib/types/extension";

export function findExtensionState(
  extensionList: ExtensionListRead | undefined,
  extensionKey: string,
): ExtensionRead | undefined {
  return extensionList?.items.find((extension) => extension.key === extensionKey);
}

export function useExtensions() {
  return useQuery({
    queryKey: queryKeys.platform.extensions.list(),
    queryFn: ({ signal }) => listExtensions(signal),
  });
}
export function useExtension(extensionKey: string) {
  const query = useExtensions();

  return {
    ...query,
    data: findExtensionState(query.data, extensionKey),
  };
}

export function invalidateFinanceWorkspaceExtensionCaches(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.extensions.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.portfolios.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.templates.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.reports.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.tools.all }),
  ]);
}

export function useToggleExtension() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      extensionKey,
      payload,
    }: {
      extensionKey: string;
      payload: ExtensionToggleRequest;
    }) => toggleExtension(extensionKey, { enabled: payload.enabled }),
    onSuccess: async (extension) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.extensions.all });

      if (extension.key === FINANCE_WORKSPACE_EXTENSION_KEY) {
        await invalidateFinanceWorkspaceExtensionCaches(queryClient);
      }
    },
  });
}
