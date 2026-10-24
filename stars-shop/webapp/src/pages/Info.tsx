import { useEffect } from "react";
import { useLocation } from "react-router";
import { useBoot } from "../components/BootContext";
import { Page, PageHeader } from "../components/Layout";
import { Card } from "../components/ui/Card";

function Paragraphs({ text }: { text: string }) {
  return (
    <div className="space-y-3 text-[14.5px] leading-relaxed text-text-2">
      {text.split(/\n+/).map((p, i) => (
        <p key={i}>{p}</p>
      ))}
    </div>
  );
}

/** Terms of purchase with the refund rules. */
export function Terms() {
  const { content } = useBoot();
  const { hash } = useLocation();
  useEffect(() => {
    if (hash === "#refund") document.getElementById("refund")?.scrollIntoView({ block: "start" });
  }, [hash]);
  return (
    <>
      <PageHeader title="Условия покупки" />
      <Page className="space-y-4">
        <Card className="p-5">
          <Paragraphs text={content.legal.terms} />
        </Card>
        <Card className="scroll-mt-20 p-5" id="refund">
          <h2 className="mb-3 font-display text-[17px] font-semibold tracking-[-0.02em]">Возврат средств</h2>
          <Paragraphs text={content.legal.refund_policy} />
        </Card>
      </Page>
    </>
  );
}
