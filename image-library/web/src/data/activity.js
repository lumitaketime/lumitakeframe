/** 資料層：掃描進度。進行中的工作，以及存在資料庫裡的工作紀錄（關掉 App 再開仍然看得到）。 */
import { api } from "../lib/api.js";

export const loadActivity = () => api("/api/activity", { quiet: true });
/** 停止一個工作；掃描與比對會保留做完的部分，之後可以繼續 */
export const stopJob = (id) => api("/api/jobs/stop", { body: { id } });
/** 暫停一個工作：停在目前的位置，之後按「繼續」接著做 */
export const pauseJob = (id) => api("/api/jobs/pause", { body: { id } });
/** 把中斷、停止或暫停的掃描、比對接著做完 */
export const resumeJob = (id) => api("/api/activity/resume", { body: { id } });
