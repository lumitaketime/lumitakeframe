/**
 * 硬碟淘汰檢查：這顆硬碟上的檔案在別顆硬碟有沒有一模一樣的副本。全部只讀，不刪不搬。
 */
import { api } from "../lib/api.js";

export const loadRetire = (rootId) => api(`/api/retire/${rootId}`, { quiet: true });
export const loadRetireAll = () => api("/api/retire", { quiet: true });
export const loadRetireFolders = (rootId, state, offset = 0) => api(`/api/retire/${rootId}/folders`, { params: { state, offset, limit: 100 }, quiet: true });
export const loadRetireFiles = (rootId, state, folder, offset = 0) =>
  api(`/api/retire/${rootId}/files`, { params: { state, folder, offset, limit: 200 }, quiet: true });
export const retirePlan = (rootId) => api(`/api/retire/${rootId}/plan`, { quiet: true });
export const startVerify = (rootId) => api(`/api/retire/${rootId}/verify`, { body: {} });
export const setPlanned = (rootId, on) => api(`/api/retire/${rootId}/planned`, { body: { on } });
export const exportRetire = (rootId, dir) => api("/api/retire/export", { body: { root_id: rootId, dir } });
export const pickExportFolder = () => api("/api/pick-folder", { body: { purpose: "export" } }).then((d) => d.path || null);
/** 整理計畫：做成一張卡（還沒開始複製），看過、按「執行」才開始 */
export const proposeConsolidate = (body) => api("/api/consolidate/propose", { body });
export const loadConsolidations = (rootId) => api("/api/consolidate", { params: { source_root: rootId }, quiet: true });
