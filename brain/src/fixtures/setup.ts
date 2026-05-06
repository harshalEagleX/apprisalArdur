import path from "node:path";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import { BackendClient } from "../state/backend";
import { config } from "../config";

const SIM_BATCHES_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".sim-batches");

export interface SimCredentials {
  id: number;
  username: string;
  password: string;
}

export interface SimReviewer extends SimCredentials {
  clientId: number;
}

export interface LoadTestFixture {
  clients: Array<{ id: number; code: string }>;
  admins: SimCredentials[];
  reviewers: SimReviewer[];
  zipPaths: string[];
}

const CLIENT_DEFS = [
  { code: "SIMCL1", name: "Sim Client Alpha" },
  { code: "SIMCL2", name: "Sim Client Beta" },
  { code: "SIMCL3", name: "Sim Client Gamma" },
  { code: "SIMCL4", name: "Sim Client Delta" },
  { code: "SIMCL5", name: "Sim Client Epsilon" },
];

const BATCH_ZIPS = [
  "SIMB001.zip",
  "SIMB002.zip",
  "SIMB003.zip",
  "SIMB004.zip",
  "SIMB005.zip",
];

export function getZipPaths(): string[] {
  return BATCH_ZIPS.map(f => {
    const p = path.join(SIM_BATCHES_DIR, f);
    if (!fs.existsSync(p)) throw new Error(`ZIP not found: ${p} — run scripts/reset-and-prep.sh first`);
    return p;
  });
}

export async function createFixtures(): Promise<LoadTestFixture> {
  const adminApi = new BackendClient();
  await adminApi.login("ADMIN", config.admin);

  // ── Clients ────────────────────────────────────────────────────────────────
  const allClients = await adminApi.getClients();
  const clients: Array<{ id: number; code: string }> = [];
  for (const def of CLIENT_DEFS) {
    const existing = allClients.find(c => c.code === def.code);
    if (existing) {
      clients.push({ id: existing.id, code: def.code });
      console.log(`[setup] client reused: ${def.code} (id=${existing.id})`);
    } else {
      const created = await adminApi.createClient(def.name, def.code);
      clients.push({ id: created.id, code: def.code });
      console.log(`[setup] client created: ${def.code} (id=${created.id})`);
    }
  }

  // ── Admin users ────────────────────────────────────────────────────────────
  const allUsers = await adminApi.getUsers();
  const admins: SimCredentials[] = [];
  for (let i = 1; i <= 5; i++) {
    const username = `sim.admin${i}`;
    const password = `SimAdmin${i}Pass!`;
    const existing = allUsers.find(u => u.username === username);
    if (existing) {
      admins.push({ id: existing.id, username, password });
      console.log(`[setup] admin reused: ${username} (id=${existing.id})`);
    } else {
      const created = await adminApi.createUser({
        username,
        password,
        role: "ADMIN",
        fullName: `Sim Admin ${i}`,
        email: `${username}@sim.local`,
      });
      admins.push({ id: created.id, username, password });
      console.log(`[setup] admin created: ${username} (id=${created.id})`);
    }
  }

  // ── Reviewer users ─────────────────────────────────────────────────────────
  const reviewers: SimReviewer[] = [];
  for (let i = 1; i <= 5; i++) {
    const username = `sim.rev${i}`;
    const password = `SimRev${i}Pass!`;
    const clientId = clients[i - 1].id;
    const existing = allUsers.find(u => u.username === username);
    if (existing) {
      reviewers.push({ id: existing.id, username, password, clientId });
      console.log(`[setup] reviewer reused: ${username} (id=${existing.id})`);
    } else {
      const created = await adminApi.createUser({
        username,
        password,
        role: "REVIEWER",
        fullName: `Sim Reviewer ${i}`,
        email: `${username}@sim.local`,
        clientId,
      });
      reviewers.push({ id: created.id, username, password, clientId });
      console.log(`[setup] reviewer created: ${username} (id=${created.id})`);
    }
  }

  await adminApi.dispose();
  return { clients, admins, reviewers, zipPaths: getZipPaths() };
}
