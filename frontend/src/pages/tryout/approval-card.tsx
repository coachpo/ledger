import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  useApproveRuntimeApproval,
  useDenyRuntimeApproval,
  useRuntimeApproval,
} from "@/hooks/use-runtime";
import type { RuntimeApprovalActionInput } from "@/lib/types/runtime";

export function TryoutApprovalCard(props: {
  approvalId: number;
  onResolved: () => Promise<void>;
}) {
  const { approvalId, onResolved } = props;
  const approvalQuery = useRuntimeApproval(approvalId);
  const approveMutation = useApproveRuntimeApproval();
  const denyMutation = useDenyRuntimeApproval();
  const isResolving = approveMutation.isPending || denyMutation.isPending;

  const resolveApproval = async (action: "approve" | "deny") => {
    const payload: RuntimeApprovalActionInput = {
      actor: "tryout-ui",
      reason:
        action === "approve"
          ? "Approved from the Tryout UI."
          : "Denied from the Tryout UI.",
    };

    try {
      if (action === "approve") {
        await approveMutation.mutateAsync({ approvalId, payload });
      } else {
        await denyMutation.mutateAsync({ approvalId, payload });
      }

      await onResolved();
      toast.success(
        action === "approve"
          ? `Approval #${approvalId} approved`
          : `Approval #${approvalId} denied`,
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to resolve approval");
    }
  };

  if (approvalQuery.isPending) {
    return <p className="text-sm text-muted-foreground">Loading approval #{approvalId}...</p>;
  }

  if (approvalQuery.isError || !approvalQuery.data) {
    return (
      <p className="text-sm text-muted-foreground">
        {approvalQuery.error instanceof Error ? approvalQuery.error.message : "Approval not found."}
      </p>
    );
  }

  const approval = approvalQuery.data;

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-muted/20 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium">Approval #{approval.approvalId}</p>
        <Badge variant="outline">{approval.status}</Badge>
        <Badge variant="secondary">{approval.capabilityKey}</Badge>
      </div>
      <div className="flex flex-col gap-1 text-sm text-muted-foreground">
        <p>Step: {approval.stepKey}</p>
        <p>Transport: {approval.summary.transport ?? "Not specified"}</p>
        <p>Display name: {approval.summary.displayName ?? "Not specified"}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {approval.allowedActions.includes("approve") ? (
          <Button
            data-testid={`tryout-approval-approve-${approval.approvalId}`}
            disabled={isResolving}
            onClick={() => resolveApproval("approve")}
            size="sm"
            variant="secondary"
          >
            Approve
          </Button>
        ) : null}
        {approval.allowedActions.includes("deny") ? (
          <Button
            data-testid={`tryout-approval-deny-${approval.approvalId}`}
            disabled={isResolving}
            onClick={() => resolveApproval("deny")}
            size="sm"
            variant="destructive"
          >
            Deny
          </Button>
        ) : null}
      </div>
    </div>
  );
}
