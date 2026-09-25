import { useEffect, useState } from "react";
export function useCatalogSearch() {
  const [text, setText] = useState(""),
    [query, setQuery] = useState(""),
    [composing, setComposing] = useState(false);
  useEffect(() => {
    if (composing) return;
    const timer = setTimeout(() => setQuery(text.trim()), 300);
    return () => clearTimeout(timer);
  }, [text, composing]);
  return {
    text,
    query,
    change: setText,
    compose: setComposing,
    submit: () => {
      if (!composing) setQuery(text.trim());
    },
  };
}
