// Dataset cells come back wrapped as { cell_id, cell_value, metadata, status, ... }.
// When cell_value is null, the old `?? cell ?? ""` pattern leaked the wrapper
// into the UI as an "Object (10 keys)" tree (TH-4979). Treat null cell_value
// as blank; only fall back to `cell` when it's not a wrapper (raw legacy values).
export const unwrapCellValue = (cell) => {
  if (cell && typeof cell === "object" && "cell_id" in cell) {
    return cell.cell_value ?? "";
  }
  return cell ?? "";
};
