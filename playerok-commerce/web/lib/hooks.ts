"use client";

import { useEffect, useState } from "react";

/** Value that follows `value` after `ms` of quiet. */
export function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/** Page number that resets to 1 whenever `filterKey` changes (no effect needed). */
export function usePage(filterKey: string): [number, (page: number) => void] {
  const [state, setState] = useState({ key: filterKey, page: 1 });
  const page = state.key === filterKey ? state.page : 1;
  return [page, (next: number) => setState({ key: filterKey, page: next })];
}

/** Local editable copy of server data; resets when the server data object changes. */
export function useDraft<S, V>(source: S | undefined, init: (s: S) => V): [V | undefined, (v: V) => void] {
  const [draft, setDraft] = useState<{ src: S; value: V }>();
  const value = source === undefined ? undefined : draft && draft.src === source ? draft.value : init(source);
  return [value, (v: V) => source !== undefined && setDraft({ src: source, value: v })];
}
