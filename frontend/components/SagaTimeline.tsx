import { Check, X, Package, Warehouse, CreditCard, CheckCircle, RotateCcw } from "lucide-react";

type OrderStatus = "PENDING" | "CONFIRMED" | "FAILED";

type StepState = "done" | "active" | "failed" | "pending";

interface Step {
  label: string;
  subtitle: string;
  icon: React.ReactNode;
  state: StepState;
  compensation?: boolean;
}

interface Props {
  status: OrderStatus;
}

function deriveSteps(status: OrderStatus): Step[] {
  const base: Step[] = [
    {
      label: "Order Created",
      subtitle: "Your order has been received",
      icon: <Package size={16} />,
      state: "done",
    },
    {
      label: "Inventory Reserved",
      subtitle: status === "FAILED" ? "Items were reserved" : "Items picked and reserved",
      icon: <Warehouse size={16} />,
      state: status === "PENDING" ? "active" : "done",
    },
    {
      label: "Payment Processed",
      subtitle:
        status === "CONFIRMED"
          ? "Payment authorized"
          : status === "FAILED"
          ? "Payment could not be processed"
          : "Awaiting payment",
      icon: <CreditCard size={16} />,
      state:
        status === "CONFIRMED"
          ? "done"
          : status === "FAILED"
          ? "failed"
          : "pending",
    },
    {
      label: "Order Confirmed",
      subtitle:
        status === "CONFIRMED"
          ? "Your order is confirmed and being prepared"
          : "Waiting for confirmation",
      icon: <CheckCircle size={16} />,
      state: status === "CONFIRMED" ? "done" : "pending",
    },
  ];

  if (status === "FAILED") {
    base.splice(3, 0, {
      label: "Inventory Released",
      subtitle: "Reserved stock has been returned",
      icon: <RotateCcw size={16} />,
      state: "done",
      compensation: true,
    });
  }

  return base;
}

function StepCircle({ state }: { state: StepState }) {
  if (state === "done") {
    return (
      <div className="w-9 h-9 rounded-full bg-success flex items-center justify-center flex-none">
        <Check size={16} className="text-white" strokeWidth={2.5} />
      </div>
    );
  }
  if (state === "failed") {
    return (
      <div className="w-9 h-9 rounded-full bg-danger flex items-center justify-center flex-none">
        <X size={16} className="text-white" strokeWidth={2.5} />
      </div>
    );
  }
  if (state === "active") {
    return (
      <div className="w-9 h-9 rounded-full border-2 border-primary bg-primary-light flex items-center justify-center flex-none">
        <span className="spinner w-4 h-4" />
      </div>
    );
  }
  // pending
  return (
    <div className="w-9 h-9 rounded-full border-2 border-border bg-surface flex items-center justify-center flex-none text-text-muted">
      <div className="w-2.5 h-2.5 rounded-full bg-border" />
    </div>
  );
}

function connectorColor(state: StepState): string {
  return state === "done" ? "bg-success" : "bg-border";
}

export default function SagaTimeline({ status }: Props) {
  const steps = deriveSteps(status);

  return (
    <div className="space-y-0">
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        return (
          <div key={step.label} className="flex gap-4">
            {/* Left: circle + connector */}
            <div className="flex flex-col items-center">
              <StepCircle state={step.state} />
              {!isLast && (
                <div
                  className={[
                    "w-0.5 flex-1 my-1 min-h-[24px]",
                    connectorColor(step.state),
                  ].join(" ")}
                />
              )}
            </div>

            {/* Right: label + subtitle */}
            <div className="pb-6 flex-1 min-w-0">
              <div className="flex items-center gap-2 mt-1.5">
                {step.compensation && (
                  <span className="badge badge-pending text-[10px]">compensation</span>
                )}
                <p
                  className={[
                    "text-sm font-semibold",
                    step.state === "done"
                      ? "text-text"
                      : step.state === "failed"
                      ? "text-danger"
                      : step.state === "active"
                      ? "text-primary"
                      : "text-text-muted",
                  ].join(" ")}
                >
                  {step.label}
                </p>
              </div>
              <p className="text-xs text-text-secondary mt-0.5">{step.subtitle}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
