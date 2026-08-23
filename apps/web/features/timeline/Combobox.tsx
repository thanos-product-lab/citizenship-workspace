"use client";

import { useEffect, useRef, useState } from "react";

import { inputStyle } from "@/components/ui";

/**
 * An editable combobox (WAI-ARIA "combobox with list autocomplete"): a text input that
 * suggests from `options` by prefix but still accepts free text. We own the dropdown
 * rather than a native <datalist> so it renders consistently below the field, matches the
 * design system, and filters by prefix (not the browser's substring matching).
 *
 * The input keeps DOM focus; the active option is tracked with `aria-activedescendant` and
 * highlighted, arrow keys move it, Enter selects, Escape closes the list (a second Escape
 * bubbles to any parent dialog). `aria-describedby` / `aria-invalid` are forwarded from the
 * enclosing Field onto the input.
 */
export function Combobox({
  id,
  value,
  options,
  onChange,
  required,
  maxLength,
  "aria-describedby": ariaDescribedBy,
  "aria-invalid": ariaInvalid,
}: {
  id: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  required?: boolean;
  maxLength?: number;
  "aria-describedby"?: string | undefined;
  "aria-invalid"?: true | undefined;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = `${id}-listbox`;
  const optionId = (i: number) => `${listboxId}-opt-${i}`;

  const query = value.trim().toLowerCase();
  const matches = query ? options.filter((o) => o.toLowerCase().startsWith(query)) : options;
  const showList = open && matches.length > 0;

  // Keep the active option scrolled into view during keyboard navigation.
  useEffect(() => {
    if (showList && activeIndex >= 0) {
      // scrollIntoView isn't implemented in jsdom (the test env) and throws there; the
      // scroll is a visual nicety, so a failure must never break the widget.
      try {
        document.getElementById(optionId(activeIndex))?.scrollIntoView({ block: "nearest" });
      } catch {
        /* no-op */
      }
    }
  }, [showList, activeIndex, listboxId]);

  function commit(name: string) {
    onChange(name);
    setOpen(false);
    setActiveIndex(-1);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setActiveIndex(matches.length ? 0 : -1);
      } else {
        setActiveIndex((i) => Math.min(matches.length - 1, i + 1));
      }
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (open) setActiveIndex((i) => Math.max(0, i - 1));
    } else if (event.key === "Enter") {
      if (open && activeIndex >= 0 && matches[activeIndex]) {
        event.preventDefault(); // select the option rather than submitting the form
        commit(matches[activeIndex]!);
      }
    } else if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        event.stopPropagation(); // close the list here; a second Escape reaches the dialog
        setOpen(false);
        setActiveIndex(-1);
      }
    }
  }

  return (
    <div
      ref={rootRef}
      onBlur={(e) => {
        // Close only when focus leaves the whole widget (not when moving to an option).
        if (!rootRef.current?.contains(e.relatedTarget as Node | null)) {
          setOpen(false);
          setActiveIndex(-1);
        }
      }}
      style={{ position: "relative", maxWidth: "24rem" }}
    >
      <input
        id={id}
        role="combobox"
        aria-expanded={showList}
        // Only advertise aria-controls while the listbox is actually in the DOM — a
        // dangling IDREF (closed / no-match state) is an ARIA 1.2 conformance error.
        {...(showList ? { "aria-controls": listboxId } : {})}
        aria-autocomplete="list"
        {...(showList && activeIndex >= 0 ? { "aria-activedescendant": optionId(activeIndex) } : {})}
        {...(ariaDescribedBy ? { "aria-describedby": ariaDescribedBy } : {})}
        {...(ariaInvalid ? { "aria-invalid": true as const } : {})}
        value={value}
        required={required}
        maxLength={maxLength}
        autoComplete="off"
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActiveIndex(-1);
        }}
        // Deliberately no onFocus-to-open: the form modal focuses this field on open, and
        // an Edit prefills it — auto-opening the list there covers the form on arrival.
        // The list opens on typing or ArrowDown, which are user intent.
        onKeyDown={onKeyDown}
        style={{ ...inputStyle, maxWidth: "100%", width: "100%" }}
      />
      {showList && (
        <ul
          id={listboxId}
          role="listbox"
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            right: 0,
            zIndex: 10,
            margin: 0,
            padding: "var(--cw-space-1)",
            listStyle: "none",
            maxHeight: "14rem",
            overflowY: "auto",
            background: "var(--cw-surface)",
            border: "1px solid var(--cw-border-strong)",
            borderRadius: "var(--cw-radius-md)",
            boxShadow: "var(--cw-shadow-md)",
          }}
        >
          {matches.map((name, i) => {
            const active = i === activeIndex;
            return (
              <li
                key={name}
                id={optionId(i)}
                role="option"
                aria-selected={active}
                onMouseDown={(e) => e.preventDefault()} // keep focus on the input
                onClick={() => commit(name)}
                onMouseEnter={() => setActiveIndex(i)}
                style={{
                  padding: "var(--cw-space-2) var(--cw-space-3)",
                  borderRadius: "var(--cw-radius-sm)",
                  cursor: "pointer",
                  background: active ? "var(--cw-surface-sunken)" : "transparent",
                }}
              >
                {name}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
