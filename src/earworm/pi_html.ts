/** Preserve HTML table relationships before Readability or textContent removes
 * their layout. Coordinates remain explicit when header markup is ambiguous.
 */
const BLOCKS = new Set(["P", "DIV", "LI", "UL", "OL", "SECTION", "ARTICLE", "PRE", "H1", "H2", "H3", "H4", "H5", "H6"]);

export function readableText(node: Node): string {
  function visit(current: Node): string {
    if (current.nodeType === 3) return current.textContent ?? "";
    const tag = (current as Element).tagName;
    if (["SCRIPT", "STYLE", "NOSCRIPT"].includes(tag)) return "";
    if (tag === "BR") return "\n";
    const text = Array.from(current.childNodes).map(visit).join("");
    return BLOCKS.has(tag) ? `\n${text}\n` : text;
  }
  return visit(node).replace(/\r\n?/g, "\n").replace(/[ \t]+/g, " ").replace(/ *\n */g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

interface Cell {
  element: Element; text: string; row: number; col: number;
  rows: number; cols: number; header: boolean; scope: string;
}

function span(cell: Element, name: string): number {
  const raw = cell.getAttribute(name);
  if (raw === null) return 1;
  return /^\d+$/.test(raw) && Number(raw) > 0 && Number(raw) <= 100 ? Number(raw) : 0;
}

function tableText(table: Element, number: number): string {
  const rows = Array.from(table.querySelectorAll("tr")).filter(row => row.closest("table") === table);
  const cells: Cell[] = [];
  const grid: (Cell | undefined)[][] = [];
  let ambiguous = rows.length > 1000;
  for (const [rowIndex, row] of rows.entries()) {
    grid[rowIndex] ??= [];
    let col = 0;
    for (const element of Array.from(row.children).filter(child => ["TD", "TH"].includes(child.tagName))) {
      while (grid[rowIndex][col]) col++;
      const cell = { element, text: readableText(element), row: rowIndex, col,
        rows: span(element, "rowspan"), cols: span(element, "colspan"),
        header: element.tagName === "TH", scope: element.getAttribute("scope") ?? "" };
      cells.push(cell);
      if (!cell.rows || !cell.cols || col + cell.cols > 200 || rowIndex + cell.rows > rows.length) {
        ambiguous = true;
        col++;
        continue;
      }
      for (let r = rowIndex; r < rowIndex + cell.rows; r++) {
        grid[r] ??= [];
        for (let c = col; c < col + cell.cols; c++) {
          if (grid[r][c]) ambiguous = true;
          grid[r][c] = cell;
        }
      }
      col += cell.cols;
    }
  }
  const caption = table.querySelector("caption");
  const lines = [`[TABLE ${number}${caption ? ": " + readableText(caption) : ""}]`];
  if (ambiguous) lines.push("AMBIGUOUS TABLE: invalid, overlapping, or unsupported spans. Preserve source coordinates below; do not infer column/category associations.");
  for (const cell of cells) {
    const explicitIds = (cell.element.getAttribute("headers") ?? "").split(/\s+/).filter(Boolean);
    const explicitHeaders = explicitIds.map(id => cells.find(c => c.element.id === id));
    const coordinates = `rows ${cell.row + 1}-${cell.row + (cell.rows || 1)}, columns ${cell.col + 1}-${cell.col + (cell.cols || 1)}`;
    if (ambiguous || explicitHeaders.some(header => !header)) {
      lines.push(`[${coordinates}; header associations ambiguous; rowspan=${cell.element.getAttribute("rowspan") ?? "1"}; colspan=${cell.element.getAttribute("colspan") ?? "1"}]\n${cell.text || "(empty)"}`);
      continue;
    }
    const columnLabels: string[] = [];
    for (let c = cell.col; c < cell.col + cell.cols; c++) {
      const labels = [];
      for (let r = 0; r < cell.row; r++) {
        const above = grid[r]?.[c];
        if (above && above !== cell && above.text &&
            (above.scope === "col" || above.scope === "colgroup" ||
             (above.header && above.scope !== "row" && above.scope !== "rowgroup") || r === 0)) {
          if (!labels.includes(above.text)) labels.push(above.text);
        }
      }
      if (labels.length) columnLabels.push(`column ${c + 1}: ${labels.join(" > ")}`);
    }
    const rowLabels = [];
    for (let r = cell.row; r < cell.row + cell.rows; r++) {
      for (let c = 0; c < cell.col; c++) {
        const left = grid[r]?.[c];
        if (left && left !== cell && left.text && (left.header || left.scope === "row" || c === 0)) {
          const label = `row ${r + 1}: ${left.text}`;
          if (!rowLabels.includes(label)) rowLabels.push(label);
        }
      }
    }
    const labels = [explicitHeaders.length ? `explicit headers: ${explicitHeaders.map(h => h?.text).join(" | ")}` : "",
      columnLabels.length ? `column labels (headers or first row): ${columnLabels.join(" | ")}` : "",
      rowLabels.length ? `row labels (headers or first column): ${rowLabels.join(" | ")}` : ""].filter(Boolean);
    lines.push(`[${coordinates}${cell.header ? "; header cell" : ""}${labels.length ? "; " + labels.join("; ") : ""}]\n${cell.text || "(empty)"}`);
    if (cell.rows > 1 || cell.cols > 1) lines.push("[Value spans the stated rows/columns together; no finer assignment is implied.]");
  }
  lines.push(`[END TABLE ${number}]`);
  return lines.join("\n\n");
}

export function preserveTables(document: Document): number {
  const tables = Array.from(document.querySelectorAll("table"));
  // Inner tables are serialized first, so outer cells retain their labels.
  for (const [index, table] of tables.map((table, index) => [index, table] as const).reverse()) {
    const replacement = document.createElement("pre");
    replacement.textContent = "\n" + tableText(table, index + 1) + "\n";
    table.replaceWith(replacement);
  }
  return tables.length;
}
