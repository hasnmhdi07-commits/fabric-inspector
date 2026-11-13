// History of checks, kept only on this device (IndexedDB). Nothing here is ever uploaded.
const DB = "fabric-inspector", STORE = "scans", KEEP = 60;
let dbp = null;

function open() {
  if (!dbp) {
    dbp = new Promise((res, rej) => {
      const q = indexedDB.open(DB, 1);
      q.onupgradeneeded = () => q.result.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      q.onsuccess = () => res(q.result);
      q.onerror = () => rej(q.error);
    });
  }
  return dbp;
}
const tx = async (mode, fn) => {
  const db = await open();
  return new Promise((res, rej) => {
    const t = db.transaction(STORE, mode), out = fn(t.objectStore(STORE));
    t.oncomplete = () => res(out && "result" in out ? out.result : undefined);
    t.onerror = t.onabort = () => rej(t.error);
  });
};

/** Newest first. */
export async function listScans() {
  const all = await tx("readonly", (s) => s.getAll());
  return (all || []).sort((a, b) => b.time - a.time);
}
export const getScan = (id) => tx("readonly", (s) => s.get(id));
export const deleteScan = (id) => tx("readwrite", (s) => s.delete(id));
export const clearScans = () => tx("readwrite", (s) => s.clear());

/** Adds one check and drops the oldest ones beyond KEEP. Returns the new id. */
export async function addScan(rec) {
  const id = await tx("readwrite", (s) => s.add(rec));
  const all = await listScans();
  for (const old of all.slice(KEEP)) await deleteScan(old.id);
  return id;
}
