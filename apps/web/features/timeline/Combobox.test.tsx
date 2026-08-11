import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Combobox } from "./Combobox";

const OPTIONS = ["Spain", "Sweden", "Switzerland", "France", "Germany"];

function Harness({ onChange }: { onChange?: (v: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <>
      <label htmlFor="dest">Destination</label>
      <Combobox
        id="dest"
        value={value}
        options={OPTIONS}
        onChange={(v) => {
          setValue(v);
          onChange?.(v);
        }}
      />
    </>
  );
}

describe("Combobox", () => {
  it("filters options by prefix as you type", () => {
    render(<Harness />);
    const input = screen.getByLabelText("Destination");
    fireEvent.change(input, { target: { value: "sw" } });

    const listbox = screen.getByRole("listbox");
    const options = within(listbox).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Sweden", "Switzerland"]); // prefix match, not substring
    expect(input).toHaveAttribute("aria-expanded", "true");
  });

  it("selects the active option with the keyboard", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const input = screen.getByLabelText("Destination");

    fireEvent.change(input, { target: { value: "s" } });
    fireEvent.keyDown(input, { key: "ArrowDown" }); // activate first (Spain)
    fireEvent.keyDown(input, { key: "ArrowDown" }); // Sweden
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onChange).toHaveBeenLastCalledWith("Sweden");
    expect((input as HTMLInputElement).value).toBe("Sweden");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument(); // closes on select
  });

  it("selects an option on click", () => {
    render(<Harness />);
    const input = screen.getByLabelText("Destination");
    fireEvent.change(input, { target: { value: "fr" } });
    fireEvent.click(screen.getByRole("option", { name: "France" }));
    expect((input as HTMLInputElement).value).toBe("France");
  });

  it("closes the list on Escape but keeps the typed text", () => {
    render(<Harness />);
    const input = screen.getByLabelText("Destination");
    fireEvent.change(input, { target: { value: "ger" } });
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect((input as HTMLInputElement).value).toBe("ger"); // free text preserved
  });

  it("shows no list when nothing matches (free text is allowed)", () => {
    render(<Harness />);
    const input = screen.getByLabelText("Destination");
    fireEvent.change(input, { target: { value: "Barcelona" } });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});
