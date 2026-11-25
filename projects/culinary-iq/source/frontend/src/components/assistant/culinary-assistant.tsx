"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Archive, ArrowUp, Camera, Clipboard, FileUp, History, Image as ImageIcon, Link as LinkIcon, LoaderCircle, MessageSquarePlus, Plus, RotateCcw, Square, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRestaurants } from "@/components/restaurants/restaurant-provider";
import {
  archiveAssistantConversation, createAssistantConversation, discardAssistantEvidenceBundle,
  getAssistantCapabilities, getAssistantConversation, listAssistantConversations, sendAssistantMessage,
  updateAssistantConversationContext, uploadAssistantEvidence, type AssistantCapabilities, type AssistantContextEnvelope,
  type AssistantConversation, type AssistantEvidenceUpload, type AssistantMessage,
} from "@/services/assistant";

const ACTIVE_KEY = "culinary-iq-active-conversation";
const suggestions = ["How do I make a post?", "Where did my imported posts go?", "What is missing for this restaurant?", "Help me get started."];
const UUID_PATTERN = /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi;
const INTERNAL_ROUTE_PATTERN = /(?:route:\s*)?\/(?:photo-iq|ad-studio|social-imports|brand-iq|campaigns|insights|menu-intelligence|visual-intelligence)(?:\?[^\s)\]]+)?/gi;
const sanitizeDisplay = (content: string) => content
  .replace(UUID_PATTERN, "the selected restaurant")
  .replace(INTERNAL_ROUTE_PATTERN, "Restaurant Setup")
  .replace(/navigation target/gi, "button")
  .replace(/read-only data returned/gi, "saved restaurant information")
  .replace(/location_count/gi, "location count");

function Inline({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return <>{parts.map((part, index) => part.startsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : part.startsWith("`") ? <code key={index} className="rounded bg-black/5 px-1 py-0.5 text-[.9em]">{part.slice(1, -1)}</code> : part)}</>;
}

function Markdown({ content }: { content: string }) {
  const lines = sanitizeDisplay(content).replace(/\r/g, "").split("\n");
  const nodes: React.ReactNode[] = [];
  let code: string[] = [];
  let inCode = false;
  lines.forEach((line, index) => {
    if (line.startsWith("```")) {
      if (inCode) { nodes.push(<pre key={`code-${index}`} className="my-2 overflow-x-auto rounded-xl bg-[#27232e] p-3 text-xs text-white"><code>{code.join("\n")}</code></pre>); code = []; }
      inCode = !inCode; return;
    }
    if (inCode) { code.push(line); return; }
    if (/^\d+\.\s/.test(line)) nodes.push(<div key={index} className="mt-1.5 flex gap-2"><span className="font-semibold text-brand">{line.match(/^\d+/)?.[0]}.</span><p><Inline text={line.replace(/^\d+\.\s*/, "")}/></p></div>);
    else if (/^[-*]\s/.test(line)) nodes.push(<div key={index} className="mt-1 flex gap-2"><span aria-hidden>•</span><p><Inline text={line.slice(2)}/></p></div>);
    else if (line.startsWith("### ")) nodes.push(<h4 key={index} className="mt-3 font-semibold"><Inline text={line.slice(4)}/></h4>);
    else if (line.startsWith("## ")) nodes.push(<h3 key={index} className="mt-3 text-sm font-semibold"><Inline text={line.slice(3)}/></h3>);
    else if (line.trim()) nodes.push(<p key={index} className="mt-1.5 first:mt-0"><Inline text={line}/></p>);
  });
  return <div className="break-words text-[13px] leading-[1.55]">{nodes}</div>;
}

export function CulinaryAssistant({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { selectedRestaurant, selectedRestaurantId, selectedLocationId } = useRestaurants();
  const pathname = usePathname();
  const search = useSearchParams();
  const [capabilities, setCapabilities] = useState<AssistantCapabilities | null>(null);
  const [conversation, setConversation] = useState<AssistantConversation | null>(null);
  const [recent, setRecent] = useState<AssistantConversation[]>([]);
  const [showRecent, setShowRecent] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [initializationRequestId, setInitializationRequestId] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [lastPrompt, setLastPrompt] = useState<string | null>(null);
  const [attachmentMenu, setAttachmentMenu] = useState(false);
  const [uploads, setUploads] = useState<AssistantEvidenceUpload[]>([]);
  const [uploading, setUploading] = useState(false);
  const [currentForm, setCurrentForm] = useState<AssistantContextEnvelope["current_form"]>(null);
  const controller = useRef<AbortController | null>(null);
  const cameraInput = useRef<HTMLInputElement>(null);
  const photoInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const shouldFollow = useRef(true);
  useEffect(() => { const receive = (event: Event) => setCurrentForm((event as CustomEvent<AssistantContextEnvelope["current_form"]>).detail); window.addEventListener("culinary-iq-form-context", receive); return () => window.removeEventListener("culinary-iq-form-context", receive); }, []);
  const feature = pathname.startsWith("/photo-iq") ? "photo iq" : pathname.startsWith("/ad-studio") ? "ad studio" : pathname === "/" ? "home" : pathname.slice(1).replaceAll("-", " ");
  const context = useMemo<AssistantContextEnvelope>(() => ({
    selected_restaurant_id: selectedRestaurantId, selected_restaurant_name: selectedRestaurant?.name ?? null,
    selected_location_id: selectedLocationId, current_route: `${pathname}${search.toString() ? `?${search}` : ""}`,
    photo_iq_view: pathname.startsWith("/photo-iq") ? search.get("view") ?? "analyze" : null,
    open_surface: open ? "assistant" : null, feature, unsaved_form: currentForm?.unsaved_values ?? {}, current_form: currentForm,
  }), [currentForm, feature, open, pathname, search, selectedLocationId, selectedRestaurant?.name, selectedRestaurantId]);

  const refreshRecent = useCallback(async () => {
    try { setRecent(await listAssistantConversations()); } catch { /* Active chat remains usable. */ }
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    let active = true;
    setInitializing(true); setError(null);
    void Promise.all([getAssistantCapabilities(abort.signal), listAssistantConversations(abort.signal)]).then(async ([caps, items]) => {
      if (!active) return;
      setCapabilities(caps); setRecent(items);
      const stored = window.localStorage.getItem(ACTIVE_KEY);
      const chosen = items.find((item) => item.id === stored) ?? items[0];
      if (chosen) {
        try { const restored = await getAssistantConversation(chosen.id, abort.signal); if (active) { setConversation(restored); window.localStorage.setItem(ACTIVE_KEY, restored.id); } }
        catch { window.localStorage.removeItem(ACTIVE_KEY); }
      }
    }).catch((reason) => {
      if (active && !(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : "Culinary IQ could not initialize.");
    }).finally(() => { if (active) setInitializing(false); });
    return () => { active = false; abort.abort(); };
  }, [initializationRequestId]);

  useEffect(() => {
    if (!conversation?.id || initializing) return;
    const abort = new AbortController();
    const timer = window.setTimeout(() => { void updateAssistantConversationContext(conversation.id, context, abort.signal).catch(() => undefined); }, 250);
    return () => { window.clearTimeout(timer); abort.abort(); };
  }, [context, conversation?.id, initializing]);

  useEffect(() => {
    if (!open || !shouldFollow.current) return;
    requestAnimationFrame(() => { const node = scrollRef.current; if (node) node.scrollTop = node.scrollHeight; });
  }, [conversation?.messages, busy, open]);

  async function ensureConversation() {
    if (conversation) return conversation;
    const created = await createAssistantConversation(context);
    setConversation(created); setRecent((items) => [created, ...items]);
    window.localStorage.setItem(ACTIVE_KEY, created.id);
    return created;
  }

  async function submit(value: string) {
    const text = value.trim();
    if (!text || busy) return;
    setBusy(true); setError(null); setLastPrompt(text); setPrompt(""); shouldFollow.current = true;
    const optimistic: AssistantMessage = { id: `pending-${Date.now()}`, conversation_id: conversation?.id ?? "pending", role: "user", content: text, response_status: "complete", model: null, navigation: [], source_refs: [], created_at: new Date().toISOString() };
    setConversation((current) => current ? { ...current, messages: [...current.messages, optimistic] } : current);
    controller.current = new AbortController();
    try {
      const active = await ensureConversation();
      const result = await sendAssistantMessage(active.id, text, context, controller.current.signal);
      setConversation(result.conversation);
      window.localStorage.setItem(ACTIVE_KEY, result.conversation.id);
      await refreshRecent();
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") setError("Generation canceled. Your question is preserved.");
      else setError(reason instanceof Error ? reason.message : "Culinary IQ could not answer. Retry safely.");
    } finally { setBusy(false); controller.current = null; }
  }

  async function intake(files: File[]) {
    if (!files.length || uploading) return;
    setAttachmentMenu(false); setUploading(true); setError(null);
    try {
      const active = await ensureConversation();
      const result = await uploadAssistantEvidence(active.id, files, selectedRestaurantId);
      setUploads((current) => [...result.files, ...current]);
      if (result.rejected) setError(`${result.rejected} ${result.rejected === 1 ? "file was" : "files were"} not accepted. Review the message below.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The files could not be uploaded."); }
    finally {
      setUploading(false);
      if (cameraInput.current) cameraInput.current.value = "";
      if (photoInput.current) photoInput.current.value = "";
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function pasteClipboard() {
    setAttachmentMenu(false);
    try {
      const items = await navigator.clipboard.read(); const files: File[] = [];
      for (const item of items) for (const type of item.types) {
        if (type.startsWith("image/")) files.push(new File([await item.getType(type)], `clipboard-${Date.now()}.${type.split("/")[1] || "png"}`, { type }));
        else if (type === "text/plain") files.push(new File([await item.getType(type)], `clipboard-${Date.now()}.txt`, { type }));
      }
      if (files.length) await intake(files); else setError("No supported image or text was found on the clipboard.");
    } catch { setError("Clipboard access is not available here. Choose a file instead."); }
  }

  function newConversation() {
    controller.current?.abort(); setConversation(null); setPrompt(""); setError(null); setShowRecent(false);
    window.localStorage.removeItem(ACTIVE_KEY);
  }

  function retryError() {
    if (lastPrompt) { void submit(lastPrompt); return; }
    setInitializationRequestId((value) => value + 1);
  }

  async function chooseConversation(id: string) {
    const selected = await getAssistantConversation(id);
    setConversation(selected); setShowRecent(false); setError(null);
    window.localStorage.setItem(ACTIVE_KEY, selected.id); shouldFollow.current = true;
  }

  async function discardEvidence(bundleId: string) {
    try { await discardAssistantEvidenceBundle(bundleId); setError(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Pending changes could not be discarded."); }
  }

  function onSubmit(event: FormEvent) { event.preventDefault(); void submit(prompt); }
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void submit(prompt); }
  }

  return <section aria-label="Culinary IQ assistant" className={`fixed z-[70] flex flex-col overflow-hidden bg-[#faf9fc] shadow-2xl transition-transform duration-200 ${open ? "translate-x-0" : "translate-x-full"} inset-0 sm:left-auto sm:w-[430px] sm:border-l sm:border-black/5`}>
    <header className="flex min-h-[68px] shrink-0 items-center gap-2 border-b border-black/5 bg-white/90 px-4 backdrop-blur-xl">
      <div className="min-w-0 flex-1"><h2 className="text-sm font-semibold">Culinary IQ</h2><p className="truncate text-[10px] text-muted-foreground">{selectedRestaurant?.name ?? "Restaurant workspace"}</p></div>
      <Button variant="ghost" size="icon" className="min-h-11 min-w-11" aria-label="New conversation" onClick={newConversation}><MessageSquarePlus className="size-4"/></Button>
      <Button variant="ghost" size="icon" className="min-h-11 min-w-11" aria-label="Recent conversations" onClick={() => setShowRecent((value) => !value)}><History className="size-4"/></Button>
      {conversation && <Button variant="ghost" size="icon" className="min-h-11 min-w-11" aria-label="Archive conversation" onClick={async () => { await archiveAssistantConversation(conversation.id); newConversation(); await refreshRecent(); }}><Archive className="size-4"/></Button>}
      <Button variant="ghost" size="icon" className="min-h-11 min-w-11" aria-label="Close assistant" onClick={onClose}><X className="size-5"/></Button>
    </header>

    {showRecent && <div className="absolute inset-x-3 top-[72px] z-10 max-h-[45dvh] overflow-y-auto rounded-2xl border border-black/5 bg-white p-2 shadow-xl">
      {recent.length ? recent.map((item) => <button key={item.id} type="button" onClick={() => void chooseConversation(item.id)} className="min-h-11 w-full rounded-xl px-3 text-left text-xs hover:bg-muted">{item.title || "Untitled conversation"}</button>) : <p className="p-3 text-xs text-muted-foreground">No saved conversations yet.</p>}
    </div>}

    <div ref={scrollRef} onScroll={(event) => { const node = event.currentTarget; shouldFollow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 96; }} className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-3 py-4 pb-6 [-webkit-overflow-scrolling:touch]">
      {initializing && <div className="flex items-center justify-center gap-2 p-8 text-xs text-muted-foreground"><LoaderCircle className="size-4 animate-spin"/>Restoring conversation…</div>}
      {!initializing && !conversation?.messages.length && <div className="px-2 py-6 text-center"><h3 className="text-lg font-semibold">What can I help with?</h3><p className="mt-2 text-xs leading-5 text-muted-foreground">Ask about this page, your restaurant information, or the next step in a workflow.</p><div className="mt-5 grid gap-2">{suggestions.map((item) => <button key={item} onClick={() => void submit(item)} className="min-h-11 rounded-xl bg-white px-3 text-left text-xs shadow-sm">{item}</button>)}</div></div>}
      {conversation?.messages.map((message) => <article key={message.id} className={`max-w-[94%] rounded-[18px] px-3.5 py-2.5 ${message.role === "user" ? "ml-auto bg-brand text-white" : "mr-auto bg-white shadow-sm"}`}>
        <Markdown content={message.content}/>
        {message.role === "assistant" && message.navigation.length > 0 && <div className="mt-2.5 space-y-2">{message.navigation.map((action, index) => <div key={`${action.action_type}-${action.evidence_bundle_id ?? action.route ?? index}`} className={action.evidence_bundle_id ? "rounded-xl bg-[#f5f2ff] p-2.5" : ""}>
          {action.evidence_bundle_id && <p className="mb-2 text-[10px] text-muted-foreground">Pending changes · Nothing has been saved.</p>}
          <div className="flex flex-wrap gap-2">
            {action.action_type === "apply_picker_to_current_form" && action.evidence_bundle_id && currentForm ? <Button size="sm" variant="outline" onClick={() => { window.dispatchEvent(new CustomEvent("culinary-iq-picker-session", { detail: { sessionId: action.evidence_bundle_id, formType: currentForm.form_type } })); onClose(); }}>{action.label}</Button> : action.route ? <Button asChild size="sm" variant="outline"><Link href={action.route} onClick={onClose}>{action.label}</Link></Button> : null}
            {action.action_type === "apply_picker_to_current_form" && action.evidence_bundle_id ? <Button size="sm" variant="ghost" onClick={onClose}>Save for later</Button> : null}
            {action.evidence_bundle_id && action.action_type !== "apply_picker_to_current_form" ? <Button size="sm" variant="ghost" onClick={() => void discardEvidence(action.evidence_bundle_id!)}><Trash2 className="size-3.5"/>Discard</Button> : null}
          </div>
        </div>)}</div>}
      </article>)}
      {busy && <div role="status" className="mr-auto flex items-center gap-2 rounded-2xl bg-white px-3.5 py-2.5 text-xs shadow-sm"><LoaderCircle className="size-4 animate-spin"/>Thinking…</div>}
      {(capabilities?.openai_configured === false || error) && <div role="alert" className="flex items-center justify-between gap-2 rounded-xl bg-amber-50 p-3 text-xs text-amber-950"><span>{error || "Culinary IQ is not configured yet."}</span>{error && <Button size="sm" variant="outline" className="min-h-11" onClick={retryError}><RotateCcw className="size-3.5"/>Retry</Button>}</div>}
      {uploads.map((item, index) => <article key={item.id ?? `${item.filename}-${index}`} className="rounded-2xl border border-black/5 bg-white p-3 text-xs shadow-sm"><div className="flex items-start gap-3"><FileUp className="mt-0.5 size-4 shrink-0 text-brand"/><div className="min-w-0 flex-1"><p className="truncate font-semibold">{item.filename}</p><p className={item.status === "ready_for_review" ? "mt-1 text-emerald-700" : "mt-1 text-amber-700"}>{item.status === "ready_for_review" ? "Ready for review" : item.status === "unsupported" ? "Unsupported" : "Could not process"}{item.duplicate ? " · Already uploaded" : ""}</p>{item.message && <p className="mt-1 text-muted-foreground">{item.message}</p>}{item.review_route && <Button asChild size="sm" variant="outline" className="mt-2"><Link href={item.review_route} onClick={onClose}>Review evidence</Link></Button>}</div></div></article>)}
    </div>

    <form onSubmit={onSubmit} className="shrink-0 border-t border-black/5 bg-white p-3 pb-[max(.75rem,env(safe-area-inset-bottom))]">
      <input ref={cameraInput} hidden type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" capture="environment" onChange={(event) => void intake(Array.from(event.target.files ?? []))}/>
      <input ref={photoInput} hidden multiple type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" onChange={(event) => void intake(Array.from(event.target.files ?? []))}/>
      <input ref={fileInput} hidden multiple type="file" accept=".jpg,.jpeg,.png,.webp,.heic,.heif,.pdf,.doc,.docx,.txt,.md,.rtf,.odt,.csv,.xls,.xlsx,.ods,.ppt,.pptx,.odp,.json,.xml,.html,.htm" onChange={(event) => void intake(Array.from(event.target.files ?? []))}/>
      <div className="relative mb-2 flex items-center">
        <Button type="button" variant="ghost" size="icon" aria-label="Add evidence" aria-expanded={attachmentMenu} className="min-h-11 min-w-11" disabled={uploading} onClick={() => setAttachmentMenu((value) => !value)}>{uploading ? <LoaderCircle className="size-4 animate-spin"/> : <Plus className="size-5"/>}</Button>
        <span className="text-xs text-muted-foreground">Add evidence</span>
        {attachmentMenu && <div className="absolute bottom-12 left-0 z-20 w-56 rounded-2xl border border-black/5 bg-white p-1.5 shadow-xl">{[
          { label: "Take Photo", icon: Camera, action: () => cameraInput.current?.click() },
          { label: "Choose Photos", icon: ImageIcon, action: () => photoInput.current?.click() },
          { label: "Choose Document", icon: FileUp, action: () => fileInput.current?.click() },
          { label: "Browse Files", icon: FileUp, action: () => fileInput.current?.click() },
          { label: "Paste Clipboard", icon: Clipboard, action: () => void pasteClipboard() },
          { label: "Paste URL", icon: LinkIcon, action: () => { setAttachmentMenu(false); setPrompt("Please review this URL: "); } },
        ].map(({label, icon: Icon, action}) => <button key={label} type="button" onClick={action} className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-xs hover:bg-muted"><Icon className="size-4"/>{label}</button>)}</div>}
      </div>
      <label htmlFor="assistant-prompt" className="sr-only">Ask Culinary IQ</label>
      <div className="rounded-[20px] border border-black/5 bg-[#faf9fc] p-2 shadow-inner"><textarea id="assistant-prompt" rows={2} value={prompt} onChange={(event) => setPrompt(event.target.value)} onKeyDown={keyDown} placeholder="Ask Culinary IQ…" className="max-h-32 min-h-12 w-full resize-none bg-transparent px-2 py-1 text-base leading-6 outline-none"/><div className="flex justify-end gap-2">{busy && <Button type="button" variant="outline" size="icon" aria-label="Cancel generation" className="min-h-11 min-w-11" onClick={() => controller.current?.abort()}><Square className="size-4"/></Button>}<Button type="submit" size="icon" aria-label="Send message" className="min-h-11 min-w-11" disabled={busy || !prompt.trim() || capabilities?.openai_configured === false}><ArrowUp className="size-5"/></Button></div></div>
    </form>
  </section>;
}
