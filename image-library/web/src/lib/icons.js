import {
  mdiImageMultiple, mdiImageMultipleOutline as _imo, mdiCompass, mdiCompassOutline as _co, mdiMap, mdiMapOutline as _mo,
  mdiFolder, mdiFolderOutline as _fo, mdiHeart as _h, mdiHeartOutline as _ho, mdiVideo, mdiVideoOutline as _vo,
  mdiToolbox, mdiToolboxOutline as _to, mdiChartBox, mdiChartBoxOutline as _cbo, mdiImageSearch, mdiImageSearchOutline as _iso,
} from "@mdi/js";

// 選取中的導覽項目用實心圖示（M3 導覽列／抽屜）：outline → filled
const FILLED = new Map([
  [_imo, mdiImageMultiple], [_co, mdiCompass], [_mo, mdiMap], [_fo, mdiFolder], [_ho, _h], [_vo, mdiVideo],
  [_to, mdiToolbox], [_cbo, mdiChartBox], [_iso, mdiImageSearch],
]);
export const filled = (path) => FILLED.get(path) || path;

export {
  mdiAlertCircleOutline, mdiArrowLeft, mdiCameraIris, mdiCamera, mdiCellphone, mdiCheck, mdiCheckCircle,
  mdiChevronLeft, mdiChevronRight, mdiChevronDown, mdiClose, mdiCogOutline, mdiCompassOutline, mdiContentCopy, mdiCreation,
  mdiDeleteOutline, mdiDotsVertical, mdiDownload, mdiFolderMoveOutline, mdiFolderOpenOutline, mdiFolderOutline,
  mdiFolderPlusOutline, mdiHarddisk, mdiHeart, mdiHeartOutline, mdiImageAlbum, mdiImageMultipleOutline,
  mdiImageOutline, mdiInformationOutline, mdiLogout, mdiMagnify, mdiMapMarkerOutline, mdiMapOutline, mdiMenu,
  mdiPencilOutline, mdiPlay, mdiPause, mdiPlayBoxMultipleOutline, mdiPlus, mdiRefresh, mdiStop, mdiTagOutline, mdiVideoOutline, mdiWeatherNight,
  mdiWhiteBalanceSunny, mdiThemeLightDark, mdiCalendarOutline, mdiFileOutline, mdiImageRemoveOutline,
  mdiMagnifyPlusOutline, mdiMagnifyMinusOutline, mdiAlbum, mdiStarFourPoints, mdiServerNetwork, mdiLockOutline,
  mdiCheckboxMarkedCircle, mdiCheckboxBlankCircleOutline, mdiPlayCircle, mdiArrowUp, mdiFolderHome,
  mdiAccountBoxOutline, mdiAccountArrowRightOutline, mdiAccountMultiplePlusOutline, mdiAccountRemoveOutline, mdiEyeOffOutline, mdiEyeOutline,
  mdiFaceRecognition, mdiTranslate, mdiImageSearchOutline, mdiViewDashboardOutline, mdiDatabaseOutline, mdiBroom,
  mdiPound, mdiBlur, mdiBrightness6, mdiCellphoneScreenshot, mdiFileExportOutline, mdiToolboxOutline, mdiCheckAll, mdiChartBoxOutline,
  mdiArrowRight, mdiFileDocumentEditOutline, mdiInformationVariantCircleOutline, mdiAlertOutline, mdiCheckCircleOutline, mdiPinOutline, mdiPinOffOutline, mdiFilterVariant, mdiSort, mdiViewGridOutline, mdiCheckBold, mdiLinkVariant, mdiDragVariant, mdiSortDescending, mdiPaw, mdiDog, mdiCat, mdiMenuOpen,
  mdiStar, mdiStarOutline, mdiCameraOutline, mdiTagMultipleOutline, mdiAccountGroupOutline, mdiTuneVariant, mdiCloseCircle, mdiFlagRemove, mdiLayers, mdiLayersOff, mdiContentDuplicate, mdiAutoFix, mdiHistory, mdiImageFilterCenterFocus,
} from "@mdi/js";
