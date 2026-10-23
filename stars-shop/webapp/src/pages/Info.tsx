import { FileText } from "lucide-react";
import { useParams } from "react-router";
import { useBoot } from "../components/BootContext";
import { Page, PageHeader } from "../components/Layout";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/States";

export function Info() {
  const { page } = useParams();
  const { content } = useBoot();
  const pages: Record<string, { title: string; text: string }> = {
    terms: { title: "Условия покупки", text: content.legal.terms },
    refund: { title: "Правила возврата", text: content.legal.refund_policy },
    payments: { title: "Способы оплаты", text: content.legal.payment_info },
  };
  const item = page ? pages[page] : undefined;
  return (
    <>
      <PageHeader title={item?.title ?? "Информация"} />
      <Page>
        {item ? (
          <Card className="p-5">
            <div className="space-y-3 text-[14.5px] leading-relaxed text-text-2">
              {item.text.split(/\n+/).map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
          </Card>
        ) : (
          <EmptyState icon={<FileText className="size-7 text-accent" />} title="Страница не найдена" />
        )}
      </Page>
    </>
  );
}
