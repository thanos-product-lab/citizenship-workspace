"use client";

import { type FormEvent, type JSX, useRef, useState } from "react";

import { buttonStyle, cardStyle, errorTextStyle, Field, inputStyle } from "@/components/ui";

import { CATEGORY_LABELS, formatBytes, UPLOADABLE_CATEGORIES } from "./library";
import { useUploadEvidence } from "./useUploadEvidence";

/**
 * The upload control.
 *
 * A native `<input type="file">`, matching `CsvImport` — no dropzone. A drop target is an
 * affordance keyboard and screen-reader users cannot use, so it can only ever be an
 * addition to a file input, never a replacement, and it is not worth the surface here.
 *
 * The client refuses an unsupported type or an oversized file **before** starting the
 * upload, but that check is a courtesy, not a control: the server refuses the same two
 * things at the presign step, and the object store refuses a mismatched content type at
 * the PUT because the type is part of the signature. Client-side validation exists so the
 * user finds out immediately, never so the server can trust it.
 *
 * `supportedMediaTypes` and `maxBytes` come from the API rather than being written here,
 * so the accept-list and the server's allowlist cannot drift into disagreeing about what
 * is uploadable.
 */
export function UploadDocument({
  caseId,
  supportedMediaTypes,
  maxBytes,
  onUploaded,
  onStarted,
}: {
  caseId: string;
  supportedMediaTypes: string[];
  maxBytes: number;
  onUploaded: (displayName: string) => void;
  onStarted: (displayName: string) => void;
}): JSX.Element {
  const upload = useUploadEvidence(caseId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<string>(UPLOADABLE_CATEGORIES[0]);
  const [displayName, setDisplayName] = useState("");
  const [fileError, setFileError] = useState<string | undefined>(undefined);

  function reset(): void {
    setFile(null);
    setDisplayName("");
    setFileError(undefined);
    if (fileRef.current) fileRef.current.value = "";
  }

  function onFile(event: FormEvent<HTMLInputElement>): void {
    const chosen = event.currentTarget.files?.[0] ?? null;
    setFileError(undefined);
    // Clear a previous failure: an alert about the last attempt sitting above a fresh
    // one reads as a verdict on the file just chosen.
    upload.reset();
    if (!chosen) {
      setFile(null);
      return;
    }
    // A rejected file is cleared from the control too, so it never names a file that
    // the form has already decided not to send.
    const reject = (message: string): void => {
      setFileError(message);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
    };
    if (!supportedMediaTypes.includes(chosen.type)) {
      return reject(
        `${chosen.type || "That file type"} is not one this product can read. It accepts PDFs and photos.`,
      );
    }
    if (chosen.size > maxBytes) {
      return reject(
        `That file is ${formatBytes(chosen.size)} and the limit is ${formatBytes(maxBytes)}.`,
      );
    }
    setFile(chosen);
    // Seed the label from the filename so the common case needs no typing. The user can
    // change it; the filename is kept separately and never becomes the storage path.
    if (!displayName) setDisplayName(chosen.name.replace(/\.[^.]+$/, ""));
  }

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!file || busy) return;
    const name = displayName.trim() || file.name;
    // Announced at the start as well as at the end. A 20 MB upload is a long silence
    // otherwise, and the control that would have carried the news is the one the user
    // just left.
    onStarted(name);
    upload.mutate(
      { file, category, displayName: name },
      {
        onSuccess: () => {
          onUploaded(name);
          reset();
          // Focus would otherwise land on <body>: the submit button is unreachable
          // again the moment `file` clears. The file input is where "add another"
          // starts, so that is where the user is put.
          fileRef.current?.focus();
        },
      },
    );
  }

  const busy = upload.isPending;

  return (
    <form
      aria-labelledby="upload-heading"
      style={{ ...cardStyle, display: "grid", gap: "var(--cw-space-4)" }}
      onSubmit={onSubmit}
    >
      <h3 id="upload-heading" style={{ margin: 0, fontSize: "var(--cw-text-base)" }}>
        Add a document
      </h3>

      <Field
        id="upload-file"
        label="Document file"
        hint={`A PDF or a photo, up to ${formatBytes(maxBytes)}. It is stored privately against this case and is never publicly reachable.`}
        error={fileError}
      >
        <input
          ref={fileRef}
          id="upload-file"
          type="file"
          className="cw-file-input"
          accept={supportedMediaTypes.join(",")}
          onChange={onFile}
          aria-disabled={busy}
        />
      </Field>

      <Field
        id="upload-category"
        label="Document type"
        hint="What kind of document this is."
      >
        <select
          id="upload-category"
          style={inputStyle}
          value={category}
          onChange={(event) => setCategory(event.currentTarget.value)}
          aria-disabled={busy}
        >
          {UPLOADABLE_CATEGORIES.map((value) => (
            <option key={value} value={value}>
              {CATEGORY_LABELS[value]}
            </option>
          ))}
        </select>
      </Field>

      <Field
        id="upload-name"
        label="Display name"
        hint="How it will appear in your library."
      >
        <input
          id="upload-name"
          type="text"
          style={inputStyle}
          value={displayName}
          maxLength={255}
          onChange={(event) => setDisplayName(event.currentTarget.value)}
          aria-disabled={busy}
        />
      </Field>

      {upload.isError ? (
        <p role="alert" style={{ margin: 0, ...errorTextStyle }}>
          That document was not uploaded, so nothing has been added to your case. You can try
          again.
        </p>
      ) : null}

      <div>
        {/* `aria-disabled`, never `disabled`: a disabled control loses focus to <body>
            the instant it is disabled, so pressing Enter on it drops the keyboard user
            out of the form for the whole length of the upload and says nothing. Guarded
            in `onSubmit` instead. Same pattern as the recheck button on Issues. */}
        <button type="submit" style={buttonStyle} aria-disabled={!file || busy}>
          {busy ? "Uploading…" : "Upload document"}
        </button>
      </div>
    </form>
  );
}
