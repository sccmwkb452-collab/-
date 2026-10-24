import { RefreshCw, TriangleAlert } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { isChunkError, reportError } from "../lib/errors";
import { Button } from "./ui/Button";

interface Props {
  children: ReactNode;
  /** Changes of this value (the current screen) clear the error. */
  resetKey?: string;
  onHome?: () => void;
}

/** No blank screen: a crashed screen shows what happened and how to recover. */
export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportError(isChunkError(error) ? "chunk" : "render", Object.assign(new Error(error.message), { stack: `${error.stack ?? ""}\n${info.componentStack ?? ""}` }));
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const chunk = isChunkError(error);
    return (
      <div className="flex min-h-[60dvh] flex-col items-center justify-center px-8 text-center" role="alert">
        <div className="flex size-16 items-center justify-center rounded-[22px] bg-danger/12 ring-1 ring-inset ring-danger/25">
          <TriangleAlert className="size-7 text-danger" />
        </div>
        <h2 className="mt-5 font-display text-[18px] font-semibold tracking-[-0.02em]">{chunk ? "Вышло обновление" : "Экран не загрузился"}</h2>
        <p className="mt-2 max-w-[300px] text-[14px] leading-relaxed text-text-2">
          {chunk ? "Магазин обновился, пока он был открыт. Перезагрузите страницу — это займёт пару секунд." : "Мы уже получили отчёт об ошибке. Попробуйте ещё раз."}
        </p>
        <div className="mt-6 flex gap-2">
          <Button icon={<RefreshCw className="size-4" />} onClick={() => (chunk ? location.reload() : this.setState({ error: null }))}>
            {chunk ? "Перезагрузить" : "Повторить"}
          </Button>
          {this.props.onHome && (
            <Button
              variant="secondary"
              onClick={() => {
                this.setState({ error: null });
                this.props.onHome?.();
              }}
            >
              На главную
            </Button>
          )}
        </div>
      </div>
    );
  }
}
