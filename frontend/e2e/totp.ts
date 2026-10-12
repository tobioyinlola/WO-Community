import { createHmac } from "node:crypto";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32Decode(text: string): Buffer {
  let bits = "";
  for (const char of text.replace(/=+$/, "").toUpperCase()) bits += ALPHABET.indexOf(char).toString(2).padStart(5, "0");
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

function base32Encode(data: Buffer): string {
  let bits = "";
  for (const byte of data) bits += byte.toString(2).padStart(8, "0");
  let out = "";
  for (let i = 0; i < bits.length; i += 5) out += ALPHABET[parseInt(bits.slice(i, i + 5).padEnd(5, "0"), 2)];
  return out;
}

/** The six digit code for a base32 key at a moment in time (RFC 6238, 30 second steps). */
export function totp(secret: string, at = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30_000)));
  const hmac = createHmac("sha1", base32Decode(secret)).update(counter).digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  const value = (hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return String(value).padStart(6, "0");
}

/** The demo admin's key, worked out from the same phrase `scripts/seed_admin_demo.py` uses. */
export const ADMIN_KEY = base32Encode(Buffer.from("wo community demo admin")).replace(/=+$/, "");

const lastStep = new Map<string, number>();

/** A code for now. The server accepts each step once, so a repeat within 30 seconds waits for the next. */
export async function freshCode(secret: string, skipAhead = false): Promise<string> {
  let step = Math.floor(Date.now() / 30_000);
  // `skipAhead` is for a retry: the code just sent may have been a repeat, so use the next step.
  const last = skipAhead ? Math.max(lastStep.get(secret) ?? 0, step) : (lastStep.get(secret) ?? 0);
  if (step <= last) {
    await new Promise((resolve) => setTimeout(resolve, (last + 1) * 30_000 - Date.now() + 500));
    step = Math.floor(Date.now() / 30_000);
  }
  lastStep.set(secret, step);
  return totp(secret);
}
