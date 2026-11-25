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
