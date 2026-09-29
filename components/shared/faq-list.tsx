import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { JsonLd } from "./json-ld";

interface FaqItem {
  id: string;
  question: string;
  answer: string;
}

export function faqSchema(items: FaqItem[]) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((f) => ({ "@type": "Question", name: f.question, acceptedAnswer: { "@type": "Answer", text: f.answer } })),
  };
}

export function FaqList({ items, withSchema = true }: { items: FaqItem[]; withSchema?: boolean }) {
  if (!items.length) {
    return <p className="rounded-2xl border border-dashed p-8 text-center text-muted-foreground">Вопросы пока не добавлены.</p>;
  }
  return (
    <>
      <Accordion type="single" collapsible className="border-t border-border">
        {items.map((f) => (
          <AccordionItem key={f.id} value={f.id}>
            <AccordionTrigger>{f.question}</AccordionTrigger>
            <AccordionContent>{f.answer}</AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
      {withSchema && (
        <JsonLd data={faqSchema(items)} />
      )}
    </>
  );
}
