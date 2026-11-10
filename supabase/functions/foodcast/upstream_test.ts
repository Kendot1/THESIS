import { assertEquals, assertStringIncludes } from "https://deno.land/std@0.168.0/testing/asserts.ts"
import { createDeadlineFetch, createSupabaseClient, runWithDeadline, statusForError } from "./upstream.ts"

Deno.test("deadline aborts an upstream request that never responds", async () => {
  await runWithDeadline(() => new Promise<Response>(() => {}), 5).then(() => { throw new Error("expected deadline abort") }, error => assertStringIncludes(error.message, "deadline exceeded"))
})

Deno.test("deadline-aware fetch aborts the actual fetch signal", async () => {
  let receivedSignal: AbortSignal | undefined
  const fetchImpl: typeof fetch = (_input, init) => { receivedSignal = init?.signal ?? undefined; return new Promise<Response>(() => {}) }
  await createDeadlineFetch(fetchImpl, 5)("https://example.test").then(() => { throw new Error("expected deadline abort") }, error => assertStringIncludes(error.message, "deadline exceeded"))
  assertEquals(receivedSignal?.aborted, true)
})

Deno.test("Supabase REST uses deadline-aware fetch", async () => {
  let called = false
  const client = createSupabaseClient((_input, _init) => { called = true; return Promise.resolve(new Response("[]", { status: 200 })) })
  const result = await client.from("products").select("id")
  assertEquals(called, true)
  assertEquals(result.error, null)
  assertEquals(result.data, [])
})

Deno.test("upstream HTTP failures keep their status class", () => {
  assertEquals(statusForError({ status: 503 }), 503)
  assertEquals(statusForError({ status: 400 }), 400)
  assertEquals(statusForError(new Error("runtime failure")), 500)
})
