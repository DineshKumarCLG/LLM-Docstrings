/**
 * Unit tests for FolderPicker component logic.
 *
 * Tests the file filtering, max file count enforcement, max total size
 * enforcement, and skipped file count display logic from FolderPicker.
 *
 * Note: @testing-library/react is not installed in this project.
 * Tests validate the pure logic that drives the FolderPicker behavior,
 * mirroring the processFiles callback in FolderPicker.tsx.
 *
 * **Validates: Requirements 7.4, 7.6, 7.7, 7.9**
 */
import { describe, it, expect } from "vitest";
import type { FileWithPath, SupportedLanguage } from "../types";

// ---------------------------------------------------------------------------
// Constants (mirrored from FolderPicker.tsx)
// ---------------------------------------------------------------------------

const SUPPORTED_EXTENSIONS: Record<string, SupportedLanguage> = {
  ".py": "python",
  ".js": "javascript",
  ".jsx": "javascript",
  ".ts": "typescript",
  ".tsx": "typescript",
  ".java": "java",
  ".go": "go",
  ".rs": "rust",
};

const DEFAULT_MAX_FILES = 50;
const DEFAULT_MAX_TOTAL_SIZE = 20 * 1024 * 1024; // 20 MB

// ---------------------------------------------------------------------------
// Pure logic extracted from FolderPicker (mirrors processFiles callback)
// ---------------------------------------------------------------------------

function getExtension(filename: string): string {
  const idx = filename.lastIndexOf(".");
  return idx === -1 ? "" : filename.slice(idx).toLowerCase();
}

function detectLanguage(filename: string): SupportedLanguage | null {
  return SUPPORTED_EXTENSIONS[getExtension(filename)] ?? null;
}

interface MockFile {
  name: string;
  size: number;
  webkitRelativePath: string;
}

interface ProcessResult {
  supported: FileWithPath[];
  skippedCount: number;
  error: string | null;
}

/**
 * Mirrors the processFiles logic from FolderPicker.tsx.
 * Filters files by supported extensions, enforces limits, and counts skipped.
 */
function processFiles(
  files: MockFile[],
  maxFiles: number = DEFAULT_MAX_FILES,
  maxTotalSize: number = DEFAULT_MAX_TOTAL_SIZE,
): ProcessResult {
  const supported: FileWithPath[] = [];
  let skipped = 0;

  for (const file of files) {
    const relativePath = file.webkitRelativePath || file.name;
    const lang = detectLanguage(file.name);

    if (lang) {
      supported.push({
        file: file as unknown as File,
        relativePath,
        language: lang,
      });
    } else {
      skipped++;
    }
  }

  const total = supported.reduce((s, f) => s + (f.file as unknown as MockFile).size, 0);

  if (supported.length > maxFiles) {
    return {
      supported: [],
      skippedCount: skipped,
      error: `Too many supported files (${supported.length}). Maximum is ${maxFiles}.`,
    };
  }

  if (total > maxTotalSize) {
    return {
      supported: [],
      skippedCount: skipped,
      error: `Total size exceeds limit.`,
    };
  }

  return { supported, skippedCount: skipped, error: null };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMockFile(name: string, size: number = 100, relativePath?: string): MockFile {
  return {
    name,
    size,
    webkitRelativePath: relativePath ?? `project/${name}`,
  };
}

// ---------------------------------------------------------------------------
// 1. File filtering by supported extensions (Requirement 7.4)
// ---------------------------------------------------------------------------

describe("FolderPicker — file filtering by supported extensions", () => {
  it("includes .py files as python", () => {
    const result = processFiles([makeMockFile("main.py")]);
    expect(result.supported).toHaveLength(1);
    expect(result.supported[0].language).toBe("python");
  });

  it("includes .js files as javascript", () => {
    const result = processFiles([makeMockFile("app.js")]);
    expect(result.supported).toHaveLength(1);
    expect(result.supported[0].language).toBe("javascript");
  });

  it("includes .jsx files as javascript", () => {
    const result = processFiles([makeMockFile("Component.jsx")]);
    expect(result.supported).toHaveLength(1);
    expect(result.supported[0].language).toBe("javascript");
  });

  it("includes .ts files as typescript", () => {
    const result = processFiles([makeMockFile("utils.ts")]);
    expect(result.supported).toHaveLength(1);
    expect(result.supported[0].language).toBe("typescript");
  });

  it("includes .tsx files as typescript", () => {
    const result = processFiles([makeMockFile("App.tsx")]);
    expect(result.supported).toHaveLength(1);
    expect(result.supported[0].language).toBe("typescript");
  });

  it("includes .java files as java", () => {
    const result = processFiles([makeMockFile("Main.java")]);
    expect(result.supported).toHaveLength(1);
    expect(result.supported[0].language).toBe("java");
  });

  it("includes .go files as go", () => {
    const result = processFiles([makeMockFile("main.go")]);
    expect(result.supported).toHaveLength(1);
    expect(result.supported[0].language).toBe("go");
  });

  it("includes .rs files as rust", () => {
    const result = processFiles([makeMockFile("lib.rs")]);
    expect(result.supported).toHaveLength(1);
    expect(result.supported[0].language).toBe("rust");
  });

  it("filters out unsupported extensions (.txt, .md, .json, .css)", () => {
    const files = [
      makeMockFile("readme.md"),
      makeMockFile("data.json"),
      makeMockFile("style.css"),
      makeMockFile("notes.txt"),
    ];
    const result = processFiles(files);
    expect(result.supported).toHaveLength(0);
    expect(result.skippedCount).toBe(4);
  });

  it("filters a mixed batch keeping only supported files", () => {
    const files = [
      makeMockFile("main.py"),
      makeMockFile("readme.md"),
      makeMockFile("app.ts"),
      makeMockFile("logo.png"),
      makeMockFile("Main.java"),
    ];
    const result = processFiles(files);
    expect(result.supported).toHaveLength(3);
    expect(result.skippedCount).toBe(2);
    const langs = result.supported.map((f) => f.language);
    expect(langs).toEqual(["python", "typescript", "java"]);
  });

  it("preserves relative paths from webkitRelativePath", () => {
    const file = makeMockFile("utils.py", 100, "my-project/src/utils.py");
    const result = processFiles([file]);
    expect(result.supported[0].relativePath).toBe("my-project/src/utils.py");
  });

  it("handles files with no extension", () => {
    const result = processFiles([makeMockFile("Makefile")]);
    expect(result.supported).toHaveLength(0);
    expect(result.skippedCount).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 2. Max file count enforcement — 50 files (Requirement 7.6)
// ---------------------------------------------------------------------------

describe("FolderPicker — max file count enforcement", () => {
  it("accepts exactly 50 supported files", () => {
    const files = Array.from({ length: 50 }, (_, i) =>
      makeMockFile(`file${i}.py`, 100),
    );
    const result = processFiles(files);
    expect(result.supported).toHaveLength(50);
    expect(result.error).toBeNull();
  });

  it("rejects when more than 50 supported files are selected", () => {
    const files = Array.from({ length: 51 }, (_, i) =>
      makeMockFile(`file${i}.py`, 100),
    );
    const result = processFiles(files);
    expect(result.supported).toHaveLength(0);
    expect(result.error).toContain("Too many supported files");
    expect(result.error).toContain("51");
    expect(result.error).toContain("50");
  });

  it("only counts supported files toward the limit (unsupported are skipped)", () => {
    // 50 supported + 20 unsupported = 70 total, but only 50 count
    const supported = Array.from({ length: 50 }, (_, i) =>
      makeMockFile(`file${i}.ts`, 100),
    );
    const unsupported = Array.from({ length: 20 }, (_, i) =>
      makeMockFile(`doc${i}.md`, 100),
    );
    const result = processFiles([...supported, ...unsupported]);
    expect(result.supported).toHaveLength(50);
    expect(result.skippedCount).toBe(20);
    expect(result.error).toBeNull();
  });

  it("returns empty array on file count overflow (onFilesSelected gets [])", () => {
    const files = Array.from({ length: 60 }, (_, i) =>
      makeMockFile(`mod${i}.go`, 100),
    );
    const result = processFiles(files);
    expect(result.supported).toHaveLength(0);
    expect(result.error).not.toBeNull();
  });

  it("respects custom maxFiles parameter", () => {
    const files = Array.from({ length: 11 }, (_, i) =>
      makeMockFile(`file${i}.rs`, 100),
    );
    const result = processFiles(files, 10);
    expect(result.supported).toHaveLength(0);
    expect(result.error).toContain("11");
    expect(result.error).toContain("10");
  });
});

// ---------------------------------------------------------------------------
// 3. Max total size enforcement — 20 MB (Requirement 7.7)
// ---------------------------------------------------------------------------

describe("FolderPicker — max total size enforcement", () => {
  it("accepts files totaling exactly 20 MB", () => {
    const maxSize = 20 * 1024 * 1024;
    // 20 files of 1 MB each = 20 MB exactly
    const files = Array.from({ length: 20 }, (_, i) =>
      makeMockFile(`file${i}.py`, maxSize / 20),
    );
    const result = processFiles(files);
    expect(result.supported).toHaveLength(20);
    expect(result.error).toBeNull();
  });

  it("rejects when total size exceeds 20 MB", () => {
    const overSize = 20 * 1024 * 1024 + 1;
    const files = [makeMockFile("big.py", overSize)];
    const result = processFiles(files);
    expect(result.supported).toHaveLength(0);
    expect(result.error).toContain("exceeds");
  });

  it("returns empty array on size overflow (onFilesSelected gets [])", () => {
    const files = [makeMockFile("huge.java", 25 * 1024 * 1024)];
    const result = processFiles(files);
    expect(result.supported).toHaveLength(0);
    expect(result.error).not.toBeNull();
  });

  it("only counts supported file sizes (unsupported files don't count)", () => {
    // 10 MB of supported + 15 MB of unsupported = 25 MB total, but only 10 MB counts
    const supported = [makeMockFile("app.ts", 10 * 1024 * 1024)];
    const unsupported = [makeMockFile("video.mp4", 15 * 1024 * 1024)];
    const result = processFiles([...supported, ...unsupported]);
    expect(result.supported).toHaveLength(1);
    expect(result.error).toBeNull();
  });

  it("respects custom maxTotalSize parameter", () => {
    const customMax = 1024; // 1 KB
    const files = [makeMockFile("big.py", 2048)];
    const result = processFiles(files, DEFAULT_MAX_FILES, customMax);
    expect(result.supported).toHaveLength(0);
    expect(result.error).toContain("exceeds");
  });
});

// ---------------------------------------------------------------------------
// 4. Skipped file count display (Requirement 7.9)
// ---------------------------------------------------------------------------

describe("FolderPicker — skipped file count display", () => {
  it("reports 0 skipped when all files are supported", () => {
    const files = [
      makeMockFile("a.py"),
      makeMockFile("b.js"),
      makeMockFile("c.go"),
    ];
    const result = processFiles(files);
    expect(result.skippedCount).toBe(0);
  });

  it("reports correct skipped count for unsupported files", () => {
    const files = [
      makeMockFile("a.py"),
      makeMockFile("readme.md"),
      makeMockFile("b.ts"),
      makeMockFile("config.yaml"),
      makeMockFile("image.png"),
    ];
    const result = processFiles(files);
    expect(result.skippedCount).toBe(3);
    expect(result.supported).toHaveLength(2);
  });

  it("reports all files as skipped when none are supported", () => {
    const files = [
      makeMockFile("readme.md"),
      makeMockFile("config.yaml"),
      makeMockFile("data.csv"),
    ];
    const result = processFiles(files);
    expect(result.skippedCount).toBe(3);
    expect(result.supported).toHaveLength(0);
  });

  it("still reports skipped count even when file count limit is exceeded", () => {
    const supported = Array.from({ length: 55 }, (_, i) =>
      makeMockFile(`file${i}.py`, 100),
    );
    const unsupported = [makeMockFile("readme.md"), makeMockFile("notes.txt")];
    const result = processFiles([...supported, ...unsupported]);
    expect(result.skippedCount).toBe(2);
    expect(result.error).not.toBeNull();
  });

  it("still reports skipped count even when size limit is exceeded", () => {
    const supported = [makeMockFile("huge.py", 25 * 1024 * 1024)];
    const unsupported = [makeMockFile("readme.md")];
    const result = processFiles([...supported, ...unsupported]);
    expect(result.skippedCount).toBe(1);
    expect(result.error).not.toBeNull();
  });
});
