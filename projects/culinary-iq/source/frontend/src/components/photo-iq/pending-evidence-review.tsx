"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronUp, LoaderCircle, RotateCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import {
  confirmAssistantEvidenceBundle, discardAssistantEvidenceBundle, getAssistantEvidenceBundle,
  type AssistantEvidenceBundle, type EvidenceLocation,
} from "@/services/assistant";

const fields: Array<[keyof EvidenceLocation, string]> = [
  ["name", "Location name"], ["address_line_1", "Address line 1"], ["address_line_2", "Address line 2"],
  ["city", "City"], ["state", "State"], ["postal_code", "Postal code"], ["country", "Country"],
  ["formatted_address", "Formatted address"], ["phone", "Phone"], ["website", "Website"], ["timezone", "Timezone"],
];
const fieldClass = "min-h-11 w-full rounded-xl border border-black/8 bg-white px-3 text-sm outline-none focus:border-brand/40 focus:ring-2 focus:ring-brand/10";

export function PendingEvidenceReview({ bundleId, onClose, onSaved }: { bundleId: string | null; onClose: () => void; onSaved: (restaurantId: string, message: string) => Promise<void> }) {
  const [bundle, setBundle] = useState<AssistantEvidenceBundle | null>(null);
  const [locations, setLocations] = useState<EvidenceLocation[]>([]);
  const [original, setOriginal] = useState<EvidenceLocation[]>([]);
  const [accepted, setAccepted] = useState<Set<number>>(new Set());
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setBundle(null); setLocations([]); setOriginal([]); setAccepted(new Set()); setExpanded(new Set()); setError(null);
    if (!bundleId) return;
    const controller = new AbortController();
    setLoading(true);
    void getAssistantEvidenceBundle(bundleId, controller.signal).then((value) => {
      setBundle(value); setLocations(value.locations); setOriginal(value.locations);
      const blocked = new Set([...value.conflicts, ...value.duplicate_warnings].map((item) => item.location_index));
      setAccepted(new Set(value.locations.map((item, index) => item._index ?? index).filter((index) => !blocked.has(index))));
      setExpanded(new Set(value.locations.map((item, index) => item._index ?? index)));
    }).catch((reason) => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : "Pending changes could not load.");
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, [bundleId]);

  const warnings = useMemo(() => new Map([...(bundle?.conflicts ?? []), ...(bundle?.duplicate_warnings ?? [])].map((item) => [item.location_index, item.message])), [bundle]);
  const selected = locations.filter((item, index) => accepted.has(item._index ?? index));
  function toggle(index: number) { setAccepted((current) => { const next = new Set(current); if (next.has(index)) next.delete(index); else next.add(index); return next; }); }
  function update(index: number, key: keyof EvidenceLocation, value: string) { setLocations((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item)); }

  async function confirm() {
    if (!bundle || !selected.length) return;
    setSaving(true); setError(null);
    try {
      const result = await confirmAssistantEvidenceBundle(bundle.id, selected.map((item) => { const location = { ...item }; delete location._index; return location; }));
      await onSaved(result.restaurant_id, `${result.created_count} location${result.created_count === 1 ? "" : "s"} added after review.${result.duplicate_count ? ` ${result.duplicate_count} duplicate${result.duplicate_count === 1 ? " was" : "s were"} skipped.` : ""}`);
      onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The reviewed locations could not be saved."); }
    finally { setSaving(false); }
  }

  async function discard() {
    if (!bundle) return;
    setSaving(true);
    try { await discardAssistantEvidenceBundle(bundle.id); onClose(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Pending changes could not be discarded."); }
    finally { setSaving(false); }
  }

  return <Sheet open={Boolean(bundleId)} onOpenChange={(open) => { if (!open && !saving) onClose(); }}><SheetContent className="inset-x-0 top-auto bottom-0 flex h-[min(94dvh,900px)] w-full max-w-none flex-col overflow-hidden rounded-t-[28px] border-x-0 border-b-0 border-t border-black/5 p-0 sm:inset-y-0 sm:left-auto sm:right-0 sm:h-full sm:max-w-2xl sm:rounded-none sm:border-l sm:border-t-0">
    <header className="shrink-0 border-b border-black/5 px-5 py-5 pr-14 sm:px-7"><SheetTitle>Review Proposed Locations</SheetTitle><SheetDescription className="mt-1 text-xs leading-5">Review each location before saving it to Restaurant Setup. Nothing has been saved yet.</SheetDescription></header>
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5 pb-32 sm:px-7">
      {loading && <p className="flex items-center gap-2 rounded-xl bg-muted p-4 text-xs"><LoaderCircle className="size-4 animate-spin"/>Loading pending changes…</p>}
      {error && <p role="alert" className="rounded-xl bg-red-50 p-4 text-xs text-red-700">{error}</p>}
      {bundle && <div className="mb-4 rounded-2xl bg-[#f4f1ff] p-4"><p className="text-xs font-semibold">Pending changes</p><p className="mt-1 text-xs text-muted-foreground">{bundle.locations.length} location{bundle.locations.length === 1 ? "" : "s"} ready for review · {bundle.source_label}</p><p className="mt-2 text-[10px] font-medium text-brand">Nothing has been saved.</p></div>}
      {locations.length > 1 && <div className="mb-3 flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => setExpanded(new Set(locations.map((item, index) => item._index ?? index)))}>Expand All</Button><Button size="sm" variant="ghost" onClick={() => setExpanded(new Set())}>Collapse All</Button><Button size="sm" variant="outline" onClick={() => setAccepted(new Set(locations.map((item, index) => item._index ?? index).filter((index) => !warnings.has(index))))}><Check className="size-3.5"/>Apply All Safe</Button></div>}
      <div className="space-y-3">{locations.map((location, itemIndex) => {
        const index = location._index ?? itemIndex; const open = expanded.has(index); const warning = warnings.get(index);
        return <section key={index} className={`rounded-2xl border bg-white ${warning ? "border-amber-200" : "border-black/5"}`}><button type="button" onClick={() => setExpanded((current) => { const next = new Set(current); if (next.has(index)) next.delete(index); else next.add(index); return next; })} className="flex min-h-14 w-full items-center gap-3 px-4 text-left"><span className="min-w-0 flex-1"><strong className="block text-sm">{location.name || location.city || `Location ${itemIndex + 1}`}</strong><span className="mt-1 block truncate text-[10px] text-muted-foreground">{location.formatted_address || [location.address_line_1, location.city, location.state].filter(Boolean).join(", ") || "Address needs review"}</span></span>{warning && <AlertTriangle className="size-4 text-amber-600"/>}{open ? <ChevronUp className="size-4"/> : <ChevronDown className="size-4"/>}</button>{open && <div className="space-y-3 border-t border-black/5 p-4">{warning && <p className="rounded-xl bg-amber-50 p-3 text-xs text-amber-900">{warning}</p>}<div className="grid gap-3 sm:grid-cols-2">{fields.map(([key, fieldLabel]) => <label key={key} className={key === "formatted_address" ? "sm:col-span-2" : ""}><span className="mb-1 block text-[10px] font-semibold text-muted-foreground">{fieldLabel}</span><input value={String(location[key] ?? "")} onChange={(event) => update(itemIndex, key, event.target.value)} className={fieldClass}/></label>)}</div><div className="flex flex-wrap gap-2"><Button type="button" size="sm" variant={accepted.has(index) ? "default" : "outline"} onClick={() => toggle(index)}>{accepted.has(index) ? <><Check className="size-3.5"/>Included</> : "Include location"}</Button><Button type="button" size="sm" variant="ghost" onClick={() => setLocations((current) => current.map((item, i) => i === itemIndex ? original[itemIndex] : item))}><RotateCcw className="size-3.5"/>Undo edits</Button></div></div>}</section>;
      })}</div>
    </div>
    {bundle && <footer className="absolute inset-x-0 bottom-0 border-t border-black/5 bg-white/95 px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur-xl sm:px-7"><div className="flex gap-2"><Button variant="ghost" className="min-h-12" disabled={saving} onClick={() => void discard()}><Trash2 className="size-4"/>Discard</Button><Button className="min-h-12 flex-1 rounded-2xl" disabled={saving || !selected.length} onClick={() => void confirm()}>{saving ? "Saving…" : `Save ${selected.length} reviewed location${selected.length === 1 ? "" : "s"}`}</Button></div></footer>}
  </SheetContent></Sheet>;
}
