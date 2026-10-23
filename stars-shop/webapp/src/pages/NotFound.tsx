import { TelegramStar } from "@starshop/shared";
import { useNavigate } from "react-router";
import { Page, PageHeader } from "../components/Layout";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/States";

export function NotFound() {
  const navigate = useNavigate();
  return (
    <>
      <PageHeader title="Не найдено" />
      <Page>
        <EmptyState icon={<TelegramStar size={30} />} title="Такой страницы нет" text="Возможно, ссылка устарела." action={<Button onClick={() => navigate("/")}>На главную</Button>} />
      </Page>
    </>
  );
}
