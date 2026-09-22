// Doc ngon ngu o phia server. Vi cookies() la dynamic API, root layout
// dung ham nay se render dong thay vi tinh — chap nhan duoc, ung dung nay
// von lay het du lieu qua fetch o client.

import { cookies } from "next/headers";

import { LOCALE_COOKIE, toLocale, type Locale } from "./config";

export async function getLocale(): Promise<Locale> {
  const jar = await cookies();
  return toLocale(jar.get(LOCALE_COOKIE)?.value);
}
