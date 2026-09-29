import { guardAdminApi } from "@/lib/auth/api";
import { prisma } from "@/lib/db";
import { csvResponse, leadsToCsv } from "@/lib/leads/export";
import { jsonError } from "@/lib/security/request";

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { admin, response } = await guardAdminApi(req, { mutation: false });
  if (response) return response;
  const { id } = await params;
  const lead = await prisma.lead.findUnique({ where: { id }, include: { project: { select: { title: true } } } });
  if (!lead) return jsonError("Заявка не найдена", 404);
  await prisma.leadEvent.create({ data: { leadId: lead.id, type: "EXPORTED", message: "Заявка экспортирована в CSV", adminId: admin.id } });
  return csvResponse(leadsToCsv([lead]), `lead-${lead.id}.csv`);
}
