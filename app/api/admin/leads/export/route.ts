import type { LeadStatus, Prisma } from "@prisma/client";
import { guardAdminApi } from "@/lib/auth/api";
import { LEAD_STATUS_ORDER } from "@/lib/constants";
import { prisma } from "@/lib/db";
import { csvResponse, leadsToCsv } from "@/lib/leads/export";

export async function GET(req: Request) {
  const { response } = await guardAdminApi(req, { mutation: false });
  if (response) return response;
  const url = new URL(req.url);
  const status = url.searchParams.get("status");
  const q = url.searchParams.get("q")?.trim().slice(0, 100);
  const where: Prisma.LeadWhereInput = {
    ...(status && LEAD_STATUS_ORDER.includes(status as LeadStatus) ? { status: status as LeadStatus } : {}),
    ...(q ? { OR: [{ name: { contains: q, mode: "insensitive" } }, { phone: { contains: q } }, { email: { contains: q, mode: "insensitive" } }] } : {}),
  };
  const leads = await prisma.lead.findMany({ where, include: { project: { select: { title: true } } }, orderBy: { createdAt: "desc" }, take: 5000 });
  return csvResponse(leadsToCsv(leads), `leads-${new Date().toISOString().slice(0, 10)}.csv`);
}
