import { Home, Setup, Library, useStudio } from "./Studio";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  ArrowLeft,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CloudUpload,
  ExternalLink,
  Film,
  FolderOpen,
  Grid2X2,
  Image as ImageIcon,
  Images,
  LayoutDashboard,
  ListFilter,
  PackageCheck,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings as SettingsIcon,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  X
} from "lucide-react";

type View = "home" | "setup" | "library" | "new" | "production" | "existing" | "settings";
type ExistingTab = "overview" | "media" | "variants";
type ExistingSection = "catalog" | "source" | "ready";

type Asset = {
  id: string;
  kind: string;
  label: string;
  path: string;
  url?: string;
  sort_order: number;
  visible?: number;
};

type Variant = {
  id: string;
  kind: "digital" | "framed" | "unframed";
  size_label: string;
  frame_label: string;
  orientation_label?: string;
  sku: string;
  sale_price_usd: number;
  quantity: number;
};

type Step = { id: number; step_key: string; label: string; status: string; progress: number; retry_count: number; error?: string };
type EventRow = { id: number; kind: string; step_key?: string; message: string; progress?: number; created_at: string };

type Product = {
  id: string;
  name: string;
  status: string;
  overall_progress: number;
  listing_id?: string;
  etsy_listing_url?: string;
  etsy_update_mode?: string;
  source_image_path?: string;
  source_image_url?: string;
  digital_download_sku?: string;
  product_folder_name?: string;
  selection_name?: string;
  etsy_shop_section_id?: string;
  variant_count?: number;
  assets: Asset[];
  variants: Variant[];
  steps: Step[];
  events: EventRow[];
  etsy_listing?: Record<string, unknown>;
};

type Settings = {
  smart_object_layer?: string;
  etsy_mode: string;
  default_quantity: number;
  default_unframed_percent: number;
  default_framed_percent: number;
  default_unframed_csv_name?: string;
  default_framed_csv_name?: string;
  include_shipping_in_profit: boolean;
  pricing_formula: string;
  gelato_retail_multiplier: number;
  required_shipping_profile_name: string;
  required_production_partner_name: string;
  selection_mockup_root?: string;
  photoshop_exe_path?: string;
  etsy_media_write_policy: string;
  auto_resume_queue_on_start: boolean;
  secret_status?: Record<string, boolean>;
};

type CatalogProduct = Product & {
  thumb_url?: string;
  image_count: number;
  video_count: number;
  has_local_source?: boolean;
};

type Pagination = { page: number; page_size: number; total: number; total_pages: number };
type Selection = { name: string; folder: string; mockup_count: number; video_count: number; ready: boolean };
type PreviewAsset = {
  id: string;
  label: string;
  path: string;
  url?: string;
  selected?: boolean;
  protected?: boolean;
  required?: boolean;
  role?: string;
  sha256?: string;
};
type MediaJob = {
  id: string;
  product_id: string;
  listing_id: string;
  selection_name: string;
  status: string;
  stage: string;
  progress: number;
  error?: string;
  approval_token?: string;
  confirmation_text: string;
  preview?: {
    images?: PreviewAsset[];
    videos?: PreviewAsset[];
    selection_name?: string;
    video_action?: "preserve" | "create" | "none";
  };
};

type BulkMockupItem = {
  id: string;
  batch_id: string;
  product_id: string;
  listing_id: string;
  product_name: string;
  selection_name: string;
  source_etsy_url?: string;
  source_rank: number;
  extracted_url?: string;
  current_thumb_url?: string;
  confidence: number;
  status: string;
  error?: string;
  media_job_id?: string;
  media_job?: MediaJob | null;
};

type BulkMockupQueue = {
  items: BulkMockupItem[];
  counts: Record<string, number>;
};

type FilePayload = { filename: string; data_url: string };

const emptySettings: Settings = {
  etsy_mode: "dry_run",
  default_quantity: 999,
  default_unframed_percent: 82,
  default_framed_percent: 67,
  include_shipping_in_profit: true,
  pricing_formula: "fixed_size_table",
  gelato_retail_multiplier: 1.2924,
  required_shipping_profile_name: "Gelato: Free shipping",
  required_production_partner_name: "Gelato",
  etsy_media_write_policy: "new_drafts_only",
  auto_resume_queue_on_start: false,
};

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "İşlem tamamlanamadı.");
  return data as T;
}

function filePayload(file: File): Promise<FilePayload> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ filename: file.name, data_url: String(reader.result) });
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    idle: "Hazır",
    queued: "Sırada",
    running: "Çalışıyor",
    done: "Tamamlandı",
    error: "Hata",
    stopped: "Durduruldu",
    ready: "Onay bekliyor",
    applying: "Etsy güncelleniyor",
    stale: "Yeniden üretilecek",
    pending: "Bekliyor",
    warning: "Uyarı",
    skipped: "Atlandı"
  };
  return labels[status] || status;
}

function formatTime(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

function money(value?: number) {
  return `$${Number(value || 0).toFixed(2)}`;
}

export default function App() {
  const studio = useStudio();
  async function refreshStudio() { await Promise.all([studio.refresh(), loadSettings(), loadSelections()]); }
  const [view, setView] = useState<View>(() => { const page = location.hash.slice(1); return ["home", "setup", "library", "new", "production", "existing", "settings"].includes(page) ? page as View : "home"; });
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const selectedProductIdRef = useRef<string | null>(null);
  const [settings, setSettings] = useState<Settings>(emptySettings);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const [catalog, setCatalog] = useState<CatalogProduct[]>([]);
  const [pagination, setPagination] = useState<Pagination>({ page: 1, page_size: 4, total: 0, total_pages: 1 });
  const [catalogSearch, setCatalogSearch] = useState("");
  const [catalogQuery, setCatalogQuery] = useState("");
  const [existingDetail, setExistingDetail] = useState<CatalogProduct | null>(null);
  const [existingTab, setExistingTab] = useState<ExistingTab>("overview");
  const [selections, setSelections] = useState<Selection[]>([]);
  const [selectionRoot, setSelectionRoot] = useState("");
  const [selectedSelection, setSelectedSelection] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [mediaJob, setMediaJob] = useState<MediaJob | null>(null);
  const [selectedPreviewAssets, setSelectedPreviewAssets] = useState<Set<string>>(new Set());
  const [confirmation, setConfirmation] = useState("");
  const [existingSection, setExistingSection] = useState<ExistingSection>("catalog");
  const [bulkSelectMode, setBulkSelectMode] = useState(false);
  const [bulkSelectedIds, setBulkSelectedIds] = useState<Set<string>>(new Set());
  const [bulkSelectionName, setBulkSelectionName] = useState("");
  const [bulkQueue, setBulkQueue] = useState<BulkMockupQueue>({ items: [], counts: {} });
  const [bulkBatchId, setBulkBatchId] = useState("");
  const [sourceReviewId, setSourceReviewId] = useState("");
  const [readyReviewId, setReadyReviewId] = useState("");

  const newImagesRef = useRef<HTMLInputElement>(null);
  const artworkRef = useRef<HTMLInputElement>(null);
  const settingsUnframedRef = useRef<HTMLInputElement>(null);
  const settingsFramedRef = useRef<HTMLInputElement>(null);

  const productionProducts = useMemo(
    () => products.filter((product) => product.etsy_update_mode !== "inventory_only"),
    [products]
  );

  const activeCount = productionProducts.filter((product) => ["queued", "running"].includes(product.status)).length;
  const remoteImages = existingDetail?.assets?.filter((asset) => asset.kind === "etsy_listing_image") || [];
  const remoteVideos = existingDetail?.assets?.filter((asset) => asset.kind === "etsy_listing_video") || [];
  const sourceQueueItems = bulkQueue.items.filter((item) =>
    ["analyzing", "awaiting_source_approval", "source_approved", "producing", "paused", "error"].includes(item.status)
  );
  const readyQueueItems = bulkQueue.items.filter((item) => ["ready_to_send", "applying"].includes(item.status));
  const sourceReviewItem = bulkQueue.items.find((item) => item.id === sourceReviewId) || null;
  const readyReviewItem = bulkQueue.items.find((item) => item.id === readyReviewId) || null;

  function showError(value: unknown) {
    setError(value instanceof Error ? value.message : String(value));
    setNotice("");
  }

  function changeView(next: View) {
    setView(next);
    location.hash = next;
    setError("");
    setNotice("");
  }

  async function loadProducts(preferredId?: string, silentDetail = false) {
    const data = await api<{ products: Product[] }>("/api/products?summary=1");
    setProducts(data.products || []);
    if (preferredId) selectedProductIdRef.current = preferredId;
    const id = preferredId || selectedProductIdRef.current;
    if (id && (!silentDetail || view === "production") && data.products.some((product) => product.id === id)) await loadProductDetail(id, silentDetail);
  }

  async function loadProductDetail(productId: string, silent = false) {
    if (!silent) setBusy("product-detail");
    try {
      const data = await api<{ products: Product[] }>(`/api/products/${productId}`);
      if (selectedProductIdRef.current === productId) setSelectedProduct(data.products?.[0] || null);
    } catch (value) {
      showError(value);
    } finally {
      if (!silent) setBusy("");
    }
  }

  function selectProductionProduct(product: Product) {
    selectedProductIdRef.current = product.id;
    setSelectedProduct(product);
    void loadProductDetail(product.id);
  }

  function setProductStatusImmediately(productId: string, status: string) {
    setProducts((current) => current.map((product) => product.id === productId ? { ...product, status } : product));
    setSelectedProduct((current) => current?.id === productId ? { ...current, status } : current);
  }

  async function loadSettings() {
    const data = await api<Settings>("/api/settings");
    setSettings({ ...emptySettings, ...data });
  }

  async function loadSelections() {
    const data = await api<{ root: string; selections: Selection[] }>("/api/selections");
    setSelectionRoot(data.root);
    setSelections(data.selections || []);
  }

  async function loadBulkMockupQueue() {
    const data = await api<BulkMockupQueue>("/api/existing-mockup-queue");
    setBulkQueue(data);
    return data;
  }

  async function loadCatalog(page = pagination.page, query = catalogQuery) {
    setBusy("catalog");
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "4", search: query });
      const data = await api<{ products: CatalogProduct[]; pagination: Pagination }>(`/api/bulk-products?${params}`);
      setCatalog(data.products || []);
      setPagination(data.pagination);
    } catch (value) {
      showError(value);
    } finally {
      setBusy("");
    }
  }

  async function refreshCatalog() {
    setBusy("catalog-refresh");
    setNotice("Etsy mağazası okunuyor. Bu işlem yalnızca verileri panele çeker.");
    try {
      const data = await api<{ seen: number; created: number; updated: number }>("/api/bulk-products/refresh", {
        method: "POST",
        body: JSON.stringify({ states: ["active"] })
      });
      setNotice(`${data.seen} Etsy ürünü okundu. Yeni: ${data.created}, güncellenen kayıt: ${data.updated}.`);
      await loadCatalog(1, catalogQuery);
    } catch (value) {
      showError(value);
    } finally {
      setBusy("");
    }
  }

  async function openExistingProduct(productId: string) {
    setBusy("existing-detail");
    setExistingDetail(null);
    setExistingTab("overview");
    setEditorOpen(false);
    setMediaJob(null);
    try {
      let data = await api<{ products: CatalogProduct[] }>(`/api/bulk-products/${productId}?refresh=0`);
      if (!data.products?.[0]?.variants?.length || !data.products?.[0]?.assets?.some((asset) => asset.kind === "etsy_listing_image")) {
        data = await api<{ products: CatalogProduct[] }>(`/api/bulk-products/${productId}?refresh=1`);
      }
      const detail = data.products?.[0] || null;
      setExistingDetail(detail);
      setSelectedSelection(detail?.selection_name || "");
      if (detail) {
        const latest = await api<{ job: MediaJob | null }>(`/api/products/${detail.id}/media-replacement/latest`);
        setMediaJob(latest.job);
        if (latest.job?.preview) selectAllPreviewAssets(latest.job);
      }
    } catch (value) {
      showError(value);
    } finally {
      setBusy("");
    }
  }

  function selectAllPreviewAssets(job: MediaJob) {
    const ids = [
      ...(job.preview?.images || []),
      ...(job.preview?.videos || [])
    ].map((item) => item.id);
    setSelectedPreviewAssets(new Set(ids));
  }

  useEffect(() => {
    void Promise.all([loadProducts(), loadSettings(), loadSelections()]).catch(showError);
  }, []);

  useEffect(() => {
    if (view === "existing") void Promise.all([loadCatalog(1), loadSelections(), loadBulkMockupQueue()]);
  }, [view]);

  useEffect(() => {
    if (view !== "existing") return;
    const active = bulkQueue.items.some((item) =>
      ["analyzing", "source_approved", "producing", "applying"].includes(item.status)
    );
    if (!active) return;
    let pending = false;
    const timer = window.setInterval(async () => {
      if (pending || document.hidden) return;
      pending = true;
      try { await loadBulkMockupQueue(); } catch (error) { showError(error); } finally { pending = false; }
    }, 3500);
    return () => window.clearInterval(timer);
  }, [view, bulkQueue.items.map((item) => `${item.id}:${item.status}`).join("|")]);

  useEffect(() => {
    if (!bulkBatchId || sourceReviewId) return;
    const next = bulkQueue.items.find(
      (item) => item.batch_id === bulkBatchId && item.status === "awaiting_source_approval"
    );
    if (next) setSourceReviewId(next.id);
  }, [bulkBatchId, sourceReviewId, bulkQueue.items]);

  const hasActiveProducts = products.some((product) => ["queued", "running"].includes(product.status));

  useEffect(() => {
    if (!hasActiveProducts) return;
    let stopped = false;
    let timer = 0;
    const refresh = async () => {
      try {
        if (!document.hidden) await loadProducts(undefined, true);
      } catch (value) {
        showError(value);
      } finally {
        if (!stopped) timer = window.setTimeout(refresh, 3500);
      }
    };
    timer = window.setTimeout(refresh, 3500);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [hasActiveProducts, view]);

  useEffect(() => {
    if (!mediaJob || !["queued", "running", "applying"].includes(mediaJob.status)) return;
    let pending = false;
    const timer = window.setInterval(async () => {
      if (pending || document.hidden) return;
      pending = true;
      try {
        const job = await api<MediaJob>(`/api/media-replacements/${mediaJob.id}`);
        setMediaJob(job);
        if (job.status === "ready") selectAllPreviewAssets(job);
        if (job.status === "done" && existingDetail) await openExistingProduct(existingDetail.id);
      } catch (value) {
        showError(value);
      }
      finally { pending = false; }
    }, 3500);
    return () => window.clearInterval(timer);
  }, [mediaJob?.id, mediaJob?.status, existingDetail?.id]);

  async function createProducts(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const files = Array.from(newImagesRef.current?.files || []);
    if (!files.length) return showError(new Error("En az bir poster görseli seçmelisin."));
    setBusy("create");
    try {
      const images = await Promise.all(files.map(filePayload));
      const endpoint = images.length > 1 ? "/api/products/bulk" : "/api/products";
      const selectionName = String(form.get("selection_name") || "");
      if (!selectionName) throw new Error("Yeni ürün için selection kategorisi seçmelisin.");
      const body = images.length > 1
        ? { name: String(form.get("name") || ""), image_files: images, selection_name: selectionName }
        : { name: String(form.get("name") || ""), image_file: images[0], selection_name: selectionName };
      const data = await api<{ products: Product[]; created_ids?: string[] }>(endpoint, {
        method: "POST",
        body: JSON.stringify(body)
      });
      const firstId = data.created_ids?.[0] || data.products?.[0]?.id;
      formElement.reset();
      await loadProducts(firstId);
      changeView("production");
      setNotice(`${images.length} ürün üretim listesine eklendi.`);
    } catch (value) {
      showError(value);
    } finally {
      setBusy("");
    }
  }

  async function startProduct(productId: string) {
    setBusy("start");
    setProductStatusImmediately(productId, "queued");
    try {
      await api(`/api/products/${productId}/start`, { method: "POST", body: "{}" });
      await loadProducts(undefined, true);
      setNotice("Ürün sıraya alındı.");
    } catch (value) {
      await loadProducts(undefined, true).catch(() => undefined);
      showError(value);
    } finally {
      setBusy("");
    }
  }

  async function stopProduct(productId: string) {
    setProductStatusImmediately(productId, "stopped");
    try {
      await api(`/api/products/${productId}/stop`, { method: "POST", body: "{}" });
      await loadProducts(undefined, true);
    } catch (value) {
      await loadProducts(undefined, true).catch(() => undefined);
      showError(value);
    }
  }

  async function stopAllProducts() {
    try {
      const data = await api<{ stopped: number }>("/api/production/stop-all", { method: "POST", body: "{}" });
      await loadProducts(undefined, true);
      setNotice(`${data.stopped} üretim durduruldu. Çalışan Photoshop işlemi de kapatıldı.`);
    } catch (value) {
      showError(value);
    }
  }

  async function updateProductionSelection(product: Product, selectionName: string) {
    try {
      await api(`/api/products/${product.id}`, {
        method: "PATCH",
        body: JSON.stringify({ selection_name: selectionName })
      });
      await loadProducts(undefined, true);
      setNotice(`${selectionName} PSD klasörü seçildi.`);
    } catch (value) {
      showError(value);
    }
  }

  async function replaceProductionSource(product: Product, file: File) {
    try {
      await api(`/api/products/${product.id}`, {
        method: "PATCH",
        body: JSON.stringify({ image_file: await filePayload(file) })
      });
      await loadProducts(undefined, true);
      setNotice("Ana görsel değiştirildi; ürün temiz olarak yeniden üretime hazır.");
    } catch (value) {
      showError(value);
    }
  }

  async function deleteProduct(product: Product) {
    if (!confirm(`“${product.name}” yalnızca panelden silinsin mi? Etsy listingine dokunulmaz.`)) return;
    try {
      await api(`/api/products/${product.id}`, { method: "DELETE" });
      selectedProductIdRef.current = null;
      setSelectedProduct(null);
      await loadProducts();
    } catch (value) {
      showError(value);
    }
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("settings");
    try {
      const form = new FormData(event.currentTarget);
      const payload: Record<string, unknown> = {
        pricing_formula: String(form.get("pricing_formula") || "margin"),
        smart_object_layer: String(form.get("smart_object_layer") || "Kare 1"),
        etsy_mode: String(form.get("etsy_mode") || "draft"),
        default_quantity: Number(form.get("default_quantity") || 999),
        default_unframed_percent: Number(form.get("default_unframed_percent") || 0),
        default_framed_percent: Number(form.get("default_framed_percent") || 0),
        include_shipping_in_profit: form.get("include_shipping_in_profit") === "on",
        gelato_retail_multiplier: Number(form.get("gelato_retail_multiplier") || 1),
        required_shipping_profile_name: String(form.get("required_shipping_profile_name") || ""),
        required_production_partner_name: String(form.get("required_production_partner_name") || ""),
        etsy_media_write_policy: String(form.get("etsy_media_write_policy") || "new_drafts_only"),
        auto_resume_queue_on_start: form.get("auto_resume_queue_on_start") === "on",
        selection_mockup_root: String(form.get("selection_mockup_root") || ""),
        photoshop_exe_path: String(form.get("photoshop_exe_path") || ""),
        etsy_keystring: String(form.get("etsy_keystring") || ""),
        etsy_shared_secret: String(form.get("etsy_shared_secret") || ""),
      };
      const unframed = settingsUnframedRef.current?.files?.[0];
      const framed = settingsFramedRef.current?.files?.[0];
      if (unframed) payload.default_unframed_csv = await filePayload(unframed);
      if (framed) payload.default_framed_csv = await filePayload(framed);
      const saved = await api<Settings>("/api/settings", { method: "POST", body: JSON.stringify(payload) });
      setSettings({ ...emptySettings, ...saved });
      await refreshStudio();
      setNotice("Ayarlar kaydedildi.");
    } catch (value) {
      showError(value);
    } finally {
      setBusy("");
    }
  }

  async function startMediaPreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!existingDetail) return;
    if (!selectedSelection) return showError(new Error("Bir selection klasörü seçmelisin."));
    const file = artworkRef.current?.files?.[0];
    if (!file && !existingDetail.has_local_source && !existingDetail.source_image_path) {
      return showError(new Error("Bu ürünün yerel ana tasarımı yok. Orijinal görseli seçmelisin."));
    }
    setBusy("preview");
    try {
      const body: Record<string, unknown> = {
        selection_name: selectedSelection
      };
      if (file) body.image_file = await filePayload(file);
      const job = await api<MediaJob>(`/api/products/${existingDetail.id}/media-replacement/preview`, {
        method: "POST",
        body: JSON.stringify(body)
      });
      setMediaJob(job);
      setEditorOpen(true);
      setNotice("Photoshop önizleme işi başladı. Bu aşamada Etsy’ye yazılmaz.");
    } catch (value) {
      showError(value);
    } finally {
      setBusy("");
    }
  }

  function togglePreviewAsset(id: string) {
    const asset = [
      ...(mediaJob?.preview?.images || []),
      ...(mediaJob?.preview?.videos || [])
    ].find((item) => item.id === id);
    if (asset?.protected || asset?.required) return;
    setSelectedPreviewAssets((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function applyMediaReplacement() {
    if (!existingDetail || !mediaJob?.approval_token) return;
    if (confirmation !== mediaJob.confirmation_text) {
      return showError(new Error(`Onay alanına tam olarak “${mediaJob.confirmation_text}” yazmalısın.`));
    }
    setBusy("apply");
    try {
      const job = await api<MediaJob>(`/api/products/${existingDetail.id}/media-replacement/${mediaJob.id}/apply`, {
        method: "POST",
        body: JSON.stringify({
          approval_token: mediaJob.approval_token,
          confirmation,
          selected_asset_ids: Array.from(selectedPreviewAssets)
        })
      });
      setMediaJob(job);
      setNotice("Onayladığın görseller ve varyasyonlar doğrudan Etsy’ye uygulanıyor.");
    } catch (value) {
      showError(value);
    } finally {
      setBusy("");
    }
  }

  async function pushExistingVariants() {
    if (!existingDetail) return;
    if (!confirm(`Listing #${existingDetail.listing_id} için paneldeki varyasyonlar Etsy'ye gönderilsin mi?`)) return;
    setBusy("variants-push");
    try {
      const data = await api<{ inventory: { enabled_products_count: number; products_count: number } }>(
        `/api/bulk-products/${existingDetail.id}/push`,
        { method: "POST", body: "{}" }
      );
      setNotice(
        `Varyasyonlar Etsy'ye gönderildi: ${data.inventory.enabled_products_count} aktif / ${data.inventory.products_count} kombinasyon.`
      );
      await openExistingProduct(existingDetail.id);
      setExistingTab("variants");
    } catch (value) {
      showError(value);
    } finally {
      setBusy("");
    }
  }

  async function openSelectionFolder(selectionName: string) {
    try {
      await api("/api/selections/open", {
        method: "POST",
        body: JSON.stringify({ selection_name: selectionName })
      });
      setNotice(`${selectionName} klasörü açıldı.`);
    } catch (value) {
      showError(value);
    }
  }

  function toggleBulkProduct(productId: string) {
    setBulkSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(productId)) next.delete(productId); else next.add(productId);
      return next;
    });
  }

  async function startBulkMockups() {
    if (!bulkSelectedIds.size) return showError(new Error("En az bir Etsy ürünü seçmelisin."));
    if (!bulkSelectionName) return showError(new Error("Tüm ürünlerde kullanılacak mockup klasörünü seçmelisin."));
    setBusy("bulk-mockup-start");
    try {
      const data = await api<BulkMockupQueue>("/api/existing-mockup-queue/start", {
        method: "POST",
        body: JSON.stringify({
          product_ids: Array.from(bulkSelectedIds),
          selection_name: bulkSelectionName
        })
      });
      const batchId = data.items[0]?.batch_id || "";
      setBulkQueue(data);
      setBulkBatchId(batchId);
      setBulkSelectedIds(new Set());
      setBulkSelectMode(false);
      setExistingSection("source");
      setNotice(`${data.items.length} ürünün ana görseli Etsy mockuplarından çıkarılıyor.`);
    } catch (value) {
      showError(value);
    } finally {
      setBusy("");
    }
  }

  async function reviewBulkSource(item: BulkMockupItem, action: "approve" | "reject" | "hold") {
    try {
      const data = await api<BulkMockupQueue>(`/api/existing-mockup-queue/${item.id}/review`, {
        method: "POST",
        body: JSON.stringify({ action })
      });
      setBulkQueue((current) => {
        const untouched = current.items.filter((row) => row.batch_id !== item.batch_id);
        return { items: [...untouched, ...data.items], counts: data.counts };
      });
      setSourceReviewId("");
      if (action === "approve") setNotice(`${item.product_name} üretim sırasına alındı.`);
      if (action === "reject") setNotice(`${item.product_name} toplu işlemden çıkarıldı.`);
    } catch (value) {
      showError(value);
    }
  }

  async function controlBulkQueue(action: "pause-all" | "resume-all") {
    try {
      const data = await api<BulkMockupQueue>(`/api/existing-mockup-queue/${action}`, { method: "POST", body: "{}" });
      setBulkQueue(data);
      setNotice(action === "pause-all" ? "Toplu üretim durduruldu; Photoshop kapatıldı." : "Durdurulan ürünler sıraya geri alındı.");
    } catch (value) {
      showError(value);
    }
  }

  async function pauseBulkItem(item: BulkMockupItem) {
    try {
      await api(`/api/existing-mockup-queue/${item.id}/pause`, { method: "POST", body: "{}" });
      await loadBulkMockupQueue();
      setNotice(`${item.product_name} durduruldu.`);
    } catch (value) {
      showError(value);
    }
  }

  async function resumeBulkItem(item: BulkMockupItem) {
    try {
      await api(`/api/existing-mockup-queue/${item.id}/resume`, { method: "POST", body: "{}" });
      await loadBulkMockupQueue();
      setNotice(`${item.product_name} yeniden sıraya alındı.`);
    } catch (value) {
      showError(value);
    }
  }

  async function replaceBulkSource(item: BulkMockupItem, file: File) {
    try {
      await api(`/api/existing-mockup-queue/${item.id}/source`, {
        method: "POST",
        body: JSON.stringify({ selection_name: item.selection_name, image_file: await filePayload(file) })
      });
      await loadBulkMockupQueue();
      setSourceReviewId(item.id);
      setNotice(`${item.product_name} için yeni ana görsel seçildi.`);
    } catch (value) {
      showError(value);
    }
  }

  async function deleteBulkItem(item: BulkMockupItem) {
    if (!confirm(`“${item.product_name}” toplu işlem listesinden silinsin mi? Etsy ürününe dokunulmaz.`)) return;
    try {
      await api(`/api/existing-mockup-queue/${item.id}`, { method: "DELETE" });
      if (sourceReviewId === item.id) setSourceReviewId("");
      if (readyReviewId === item.id) setReadyReviewId("");
      await loadBulkMockupQueue();
      setNotice("Ürün işlem listesinden silindi.");
    } catch (value) {
      showError(value);
    }
  }

  async function applyBulkReady(item: BulkMockupItem) {
    if (!confirm(`${item.product_name} için önizlenen yeni görseller Etsy'ye gönderilsin mi? Video ve varyasyonlara dokunulmayacak.`)) return;
    setBusy(`bulk-apply-${item.id}`);
    try {
      await api(`/api/existing-mockup-queue/${item.id}/apply`, { method: "POST", body: "{}" });
      setReadyReviewId("");
      await loadBulkMockupQueue();
      setNotice(`${item.product_name} Etsy güncelleme sırasına alındı.`);
    } catch (value) {
      showError(value);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">e<span>2</span></div>
          <div><strong>etsy ekosistem</strong><span>LOCAL STUDIO <b>V2</b></span></div>
        </div>

        <div className="workspace-label"><span>ÇALIŞMA ALANI</span><strong>{studio.status?.workspace_name || "Benim stüdyom"}</strong></div>
        <nav className="nav-list" aria-label="Ana menü">
          <NavButton active={view === "home"} icon={<LayoutDashboard />} label="Genel bakış" onClick={() => changeView("home")} />
          <NavButton active={view === "new"} icon={<Plus />} label="Yeni ürün" onClick={() => changeView("new")} />
          <NavButton active={view === "production"} icon={<Play />} label="Üretim akışı" count={activeCount} onClick={() => changeView("production")} />
          <NavButton active={view === "existing"} icon={<Grid2X2 />} label="Mevcut ürünler" onClick={() => changeView("existing")} />
          <span className="nav-section-label">STÜDYO</span>
          <NavButton active={view === "library"} icon={<Images />} label="Şablon kütüphanesi" onClick={() => changeView("library")} />
          <NavButton active={view === "setup"} icon={<ShieldCheck />} label="Kurulum & bağlantı" onClick={() => changeView("setup")} />
          <NavButton active={view === "settings"} icon={<SettingsIcon />} label="Gelişmiş ayarlar" onClick={() => changeView("settings")} />
        </nav>

        <div className="sidebar-note"><Sparkles/><strong>Kendi ritminde üret.</strong><p>Tasarımların ve dosyaların<br/>bu bilgisayarda.</p><button onClick={() => changeView("library")}>Kütüphaneni oluştur →</button></div>
        <div className="sidebar-status">
          <span className={`connection-dot ${settings.secret_status?.etsy_access_token ? "online" : ""}`} />
          <div><strong>Etsy bağlantısı</strong><span>{settings.secret_status?.etsy_access_token ? "Bağlı" : "Kontrol gerekli"}</span></div>
        </div>
      </aside>

      <main className="content">
        <div className="studio-topbar"><span>Stüdyo <ChevronRight size={13}/><b>{{home:"Genel bakış",new:"Yeni ürün",production:"Üretim akışı",existing:"Mevcut ürünler",library:"Şablon kütüphanesi",setup:"Kurulum & bağlantı",settings:"Gelişmiş ayarlar"}[view]}</b></span><div><span className="mode-pill">{studio.status?.mode === "draft" ? "Etsy taslak modu" : "Deneme modu"}</span><span className="avatar">{(studio.status?.workspace_name || "S").slice(0,1).toUpperCase()}</span></div></div>
        {studio.error ? <div className="inline-message error" role="alert">{studio.error}</div> : null}
        {view === "home" ? <Home status={studio.status} refresh={refreshStudio} onNavigate={changeView} products={productionProducts} /> : null}
        {view === "setup" ? <Setup status={studio.status} refresh={refreshStudio} onNavigate={changeView} /> : null}
        {view === "library" ? <Library status={studio.status} refresh={refreshStudio} onNavigate={changeView} /> : null}
        {notice ? <div className="toast success"><span>{notice}</span><button aria-label="Kapat" onClick={() => setNotice("")}><X /></button></div> : null}
        {error ? <div className="toast error"><span>{error}</span><button aria-label="Kapat" onClick={() => setError("")}><X /></button></div> : null}

        {view === "new" ? (
          <NewProductView settings={settings} busy={busy === "create"} products={productionProducts} selections={selections} inputRef={newImagesRef} onSubmit={createProducts} onProduction={() => changeView("production")} />
        ) : null}

        {view === "production" ? (
          <ProductionView
            products={productionProducts}
            selected={selectedProduct}
            loading={busy === "product-detail"}
            selections={selections}
            onSelect={selectProductionProduct}
            onStart={(product) => void startProduct(product.id)}
            onStop={(product) => void stopProduct(product.id)}
            onStopAll={() => void stopAllProducts()}
            onSelection={(product, selectionName) => void updateProductionSelection(product, selectionName)}
            onSource={(product, file) => void replaceProductionSource(product, file)}
            onDelete={(product) => void deleteProduct(product)}
          />
        ) : null}

        {view === "existing" ? (
          <ExistingProductsView
            products={catalog}
            pagination={pagination}
            search={catalogSearch}
            loading={busy === "catalog" || busy === "catalog-refresh" || busy === "existing-detail"}
            detail={existingDetail}
            detailTab={existingTab}
            remoteImages={remoteImages}
            remoteVideos={remoteVideos}
            selections={selections}
            selectionRoot={selectionRoot}
            selectedSelection={selectedSelection}
            editorOpen={editorOpen}
            mediaJob={mediaJob}
            selectedAssets={selectedPreviewAssets}
            confirmation={confirmation}
            artworkRef={artworkRef}
            section={existingSection}
            sourceQueueItems={sourceQueueItems}
            readyQueueItems={readyQueueItems}
            bulkSelectMode={bulkSelectMode}
            bulkSelectedIds={bulkSelectedIds}
            bulkSelectionName={bulkSelectionName}
            sourceReviewItem={sourceReviewItem}
            readyReviewItem={readyReviewItem}
            onSearchChange={setCatalogSearch}
            onSearch={(event) => { event.preventDefault(); setCatalogQuery(catalogSearch); void loadCatalog(1, catalogSearch); }}
            onPage={(page) => void loadCatalog(page)}
            onRefresh={() => void refreshCatalog()}
            onOpen={(product) => void openExistingProduct(product.id)}
            onBack={() => { setExistingDetail(null); setExistingTab("overview"); setEditorOpen(false); setMediaJob(null); }}
            onDetailTab={setExistingTab}
            onEditorOpen={() => { setEditorOpen(true); setExistingTab("media"); }}
            onEditorClose={() => setEditorOpen(false)}
            onSelection={setSelectedSelection}
            onOpenSelection={(name) => void openSelectionFolder(name)}
            onReloadSelections={() => void loadSelections()}
            onPreview={startMediaPreview}
            onToggleAsset={togglePreviewAsset}
            onConfirmation={setConfirmation}
            onApply={() => void applyMediaReplacement()}
            onPushVariants={() => void pushExistingVariants()}
            onSection={setExistingSection}
            onToggleBulkMode={() => { setBulkSelectMode((value) => !value); setBulkSelectedIds(new Set()); }}
            onToggleBulkProduct={toggleBulkProduct}
            onBulkSelection={setBulkSelectionName}
            onStartBulk={() => void startBulkMockups()}
            onReviewSource={setSourceReviewId}
            onReviewSourceAction={(item, action) => void reviewBulkSource(item, action)}
            onCloseSourceReview={() => setSourceReviewId("")}
            onReviewReady={setReadyReviewId}
            onApplyReady={(item) => void applyBulkReady(item)}
            onCloseReadyReview={() => setReadyReviewId("")}
            onPauseAll={() => void controlBulkQueue("pause-all")}
            onResumeAll={() => void controlBulkQueue("resume-all")}
            onPauseItem={(item) => void pauseBulkItem(item)}
            onResumeItem={(item) => void resumeBulkItem(item)}
            onReplaceSource={(item, file) => void replaceBulkSource(item, file)}
            onDeleteQueueItem={(item) => void deleteBulkItem(item)}
          />
        ) : null}


        {view === "settings" ? (
          <SettingsView settings={settings} busy={busy === "settings"} unframedRef={settingsUnframedRef} framedRef={settingsFramedRef} onSubmit={saveSettings} />
        ) : null}
      </main>
    </div>
  );
}

function NavButton(props: { active: boolean; icon: React.ReactNode; label: string; count?: number; onClick: () => void }) {
  return <button className={`nav-button ${props.active ? "active" : ""}`} onClick={props.onClick}><span className="nav-icon">{props.icon}</span><span>{props.label}</span>{props.count ? <b>{props.count}</b> : null}</button>;
}

function PageHeader(props: { eyebrow: string; title: string; text: string; actions?: React.ReactNode }) {
  return <header className="page-header"><div><span className="eyebrow">{props.eyebrow}</span><h1>{props.title}</h1><p>{props.text}</p></div>{props.actions ? <div className="header-actions">{props.actions}</div> : null}</header>;
}

function NewProductView(props: { settings: Settings; busy: boolean; products: Product[]; selections: Selection[]; inputRef: React.RefObject<HTMLInputElement | null>; onSubmit: (event: FormEvent<HTMLFormElement>) => void; onProduction: () => void }) {
  return <div className="view-stack">
    <PageHeader eyebrow="YENİ LİSTİNG" title="Posterlerini üretime hazırla" text="Bir veya daha fazla ana görsel seç. Her görsel ayrı ürün olarak açılır ve varsayılan CSV ayarları otomatik uygulanır." />
    <section className="new-product-layout">
      <form className="upload-panel" onSubmit={props.onSubmit}>
        <div className="upload-illustration">+</div>
        <h2>Poster görsellerini seç</h2>
        <p>PNG veya JPG dosyalarını tek seferde seçebilirsin.</p>
        <label className="field">Ürün adı <input name="name" placeholder="Boş kalırsa dosya adı kullanılır" /></label>
        <label className="field">Selection kategorisi
          <select name="selection_name" defaultValue="" required>
            <option value="" disabled>Kategori seç</option>
            {props.selections.filter((selection) => selection.ready).map((selection) => <option key={selection.name} value={selection.name}>{selection.name}</option>)}
          </select>
          <small>Şablon kütüphanesindeki hazır koleksiyonlarından birini seç. Liste boşsa önce bir koleksiyon ekle.</small>
        </label>
        <label className="file-picker"><input ref={props.inputRef} type="file" accept="image/*" multiple /><span>Bilgisayardan gözat</span></label>
        <button className="button primary large" disabled={props.busy}>{props.busy ? "Ürünler oluşturuluyor..." : "Ürünleri oluştur"}</button>
      </form>
      <aside className="setup-summary">
        <h2>Otomatik uygulanacaklar</h2>
        <SummaryLine label="Fiyat dosyaları" value="Ayarlardaki framed / unframed CSV" />
        <SummaryLine label="Stok" value={`${props.settings.default_quantity} adet`} />
        <SummaryLine label="Kargo" value={props.settings.required_shipping_profile_name || "Ayarlardan seç"} />
        <SummaryLine label="Durum" value={props.settings.etsy_mode === "draft" ? "Etsy taslak" : "Deneme · Etsy’ye gönderilmez"} />
        <SummaryLine label="Etsy metni" value="Poster · manuel düzenlenecek" />
        <div className="recent-box"><span>Paneldeki üretim</span><strong>{props.products.length} ürün</strong><button className="text-link" type="button" onClick={props.onProduction}>Üretim akışını aç →</button></div>
      </aside>
    </section>
  </div>;
}

function SummaryLine({ label, value }: { label: string; value: string }) {
  return <div className="summary-line"><span className="check-symbol">✓</span><div><strong>{label}</strong><span>{value}</span></div></div>;
}

type ProductionProps = {
  products: Product[];
  selected: Product | null;
  loading: boolean;
  selections: Selection[];
  onSelect: (product: Product) => void;
  onStart: (product: Product) => void;
  onStop: (product: Product) => void;
  onStopAll: () => void;
  onSelection: (product: Product, selectionName: string) => void;
  onSource: (product: Product, file: File) => void;
  onDelete: (product: Product) => void;
};

function ProductionView(props: ProductionProps) {
  const hasActive = props.products.some((product) => ["queued", "running"].includes(product.status));
  return <div className="view-stack">
    <PageHeader eyebrow="ÜRETİM" title="Üretim akışı" text="Ürünleri sıraya al, ilerlemeyi izle ve Photoshop çıktılarından Etsy’ye gidecek mockupları kontrol et." />
    <div className="production-toolbar"><button className="button danger" disabled={!hasActive} onClick={props.onStopAll}><Pause /> Tüm üretimi durdur</button></div>
    <section className="production-layout">
      <aside className="job-list-panel">
        <div className="panel-heading"><div><h2>Ürünler</h2><span>{props.products.length} kayıt</span></div></div>
        <div className="job-list">
          {props.products.map((product) => <button key={product.id} className={`job-row ${props.selected?.id === product.id ? "active" : ""}`} onClick={() => props.onSelect(product)}>
            <div className="job-thumb">{product.source_image_url ? <img src={product.source_image_url.startsWith("/uploads/") ? `${product.source_image_url}?preview=1` : product.source_image_url} alt="" loading="lazy" decoding="async" /> : <span>—</span>}</div>
            <div className="job-copy"><strong>{product.name}</strong><span>{statusLabel(product.status)} · {product.variant_count || 0} varyasyon</span><div className="mini-meter"><i style={{ width: `${product.overall_progress || 0}%` }} /></div></div>
            <b>{product.overall_progress || 0}%</b>
          </button>)}
          {!props.products.length ? <div className="empty-compact">Henüz üretim ürünü yok.</div> : null}
        </div>
      </aside>
      <div className="job-detail-panel">
        {props.loading ? <Loading label="Ürün ayrıntısı yükleniyor" /> : props.selected ? <ProductDetail {...props} product={props.selected} /> : <EmptyState title="Bir ürün seç" text="İlerleme, mockuplar, video ve varyasyonlar burada görünür." />}
      </div>
    </section>
  </div>;
}

function ProductDetail(props: ProductionProps & { product: Product }) {
  const mockups = props.product.assets?.filter((asset) => asset.kind === "mockup" || asset.kind === "static_listing_image") || [];
  const videos = props.product.assets?.filter((asset) => asset.kind === "video") || [];
  const active = ["running", "queued"].includes(props.product.status);
  const locked = active;
  const actionLabel = active ? "Durdur" : props.product.overall_progress > 0 ? "Devam Et" : "Başlat";
  return <div className="detail-stack">
    <div className="detail-title-row"><div><span className={`status-pill ${props.product.status}`}>{statusLabel(props.product.status)}</span><h2>{props.product.name}</h2><p>SKU: <code>{props.product.digital_download_sku || "-"}</code></p></div><div className="button-row"><button className={`button ${active ? "danger" : "primary"}`} onClick={() => active ? props.onStop(props.product) : props.onStart(props.product)}>{active ? <X /> : <Play />}{actionLabel}</button><button className="button danger-quiet" onClick={() => props.onDelete(props.product)}>Panelden sil</button></div></div>
    <section className="production-inputs">
      <label className="field">Kategori / PSD klasörü
        <select value={props.product.selection_name || ""} disabled={locked} onChange={(event) => props.onSelection(props.product, event.target.value)}>
          <option value="">Kategori seç</option>
          {props.selections.filter((selection) => selection.ready).map((selection) => <option key={selection.name} value={selection.name}>{selection.name} · {selection.mockup_count} PSD</option>)}
        </select>
      </label>
      <label className={`button quiet file-button ${locked ? "disabled" : ""}`}><Upload /> Ana görseli değiştir
        <input type="file" accept="image/png,image/jpeg" disabled={locked} onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) props.onSource(props.product, file);
          event.currentTarget.value = "";
        }} />
      </label>
      <small>{active ? "Üretimi durdurduktan sonra değiştirebilirsin." : "Bu kategori içindeki PSD ve video şablonları kullanılacak. Mevcut aktif Etsy ürünleri bu ekrandan değiştirilemez."}</small>
    </section>
    <div className="progress-card"><div><span>Genel ilerleme</span><strong>{props.product.overall_progress || 0}%</strong></div><div className="large-meter"><i style={{ width: `${props.product.overall_progress || 0}%` }} /></div></div>
    <LiveProcessTracker product={props.product} />
    <div className="info-grid"><Metric label="Varyasyon" value={String(props.product.variants?.length || 0)} /><Metric label="Mockup" value={String(mockups.length)} /><Metric label="Video" value={String(videos.length)} /><Metric label="Etsy" value={props.product.listing_id ? `Draft ${props.product.listing_id}` : "Bekliyor"} /></div>
    <section className="detail-section"><div className="section-heading"><div><h3>Mockup ve video</h3><span>Photoshop çıktıları</span></div></div>{mockups.length ? <div className="media-grid compact">{mockups.map((asset) => <figure key={asset.id}><img src={`${asset.url}?preview=1`} alt={asset.label} loading="lazy" decoding="async" /><figcaption>{asset.label}</figcaption></figure>)}</div> : <EmptyState title="Mockup henüz üretilmedi" text="Ürünü sıraya aldığında çıktılar burada görünür." />}{videos.map((asset) => <video key={asset.id} className="wide-video" src={asset.url} controls muted preload="none" />)}</section>
    <section className="detail-section"><div className="section-heading"><div><h3>Varyasyon özeti</h3><span>{props.product.variants?.length || 0} satır</span></div></div><VariantSummary variants={props.product.variants || []} /></section>
    <section className="detail-section"><div className="section-heading"><div><h3>Son işlemler</h3><span>Yeni kayıtlar üstte görünür</span></div></div><div className="event-list wide">{props.product.events?.slice(0, 18).map((event) => <div className={`event-row ${event.kind}`} key={event.id}><strong>{event.message}</strong><span>{event.progress !== undefined && event.progress !== null ? `${event.progress}% · ` : ""}{formatTime(event.created_at)}</span></div>)}</div></section>
  </div>;
}

const LIVE_STEPS = [
  { key: "validate", title: "Görsel kontrol ediliyor" },
  { key: "photoshop_prepare", title: "Photoshop hazırlanıyor" },
  { key: "mockup_render", title: "Mockuplar üretiliyor" },
  { key: "video_mockup", title: "Video hazırlanıyor" },
  { key: "etsy_draft", title: "Etsy'ye aktarılıyor" },
  { key: "cost_finalize", title: "İşlem tamamlanıyor" }
];

function LiveStepIcon({ stepKey }: { stepKey: string }) {
  if (stepKey === "video_mockup") return <Film />;
  if (stepKey === "etsy_draft") return <PackageCheck />;
  if (stepKey === "mockup_render") return <Images />;
  if (stepKey === "validate") return <Search />;
  if (stepKey === "cost_finalize") return <Check />;
  return <Sparkles />;
}

function LiveProcessTracker({ product }: { product: Product }) {
  const stepMap = new Map((product.steps || []).map((step) => [step.step_key, step]));
  const current = LIVE_STEPS.find((item) => item.key === product.steps?.find((step) => step.status === "running")?.step_key);
  return <section className="detail-section live-process-board">
    <div className="section-heading"><div><h3>Canlı işlem takibi</h3><span>{current ? current.title : product.status === "done" ? "Tüm işlemler tamamlandı" : "Adımlar sırayla çalışacak"}</span></div><span className={`live-indicator ${product.status}`}>{["running", "queued"].includes(product.status) ? <i /> : null}{statusLabel(product.status)}</span></div>
    <div className="live-step-grid">{LIVE_STEPS.map((definition) => {
      const step = stepMap.get(definition.key);
      const status = step?.status || "pending";
      const progress = Math.max(0, Math.min(100, Number(step?.progress || 0)));
      const latestEvent = (product.events || []).find((event) => event.step_key === definition.key);
      const detail = status === "pending" ? "Sırada bekliyor" : status === "skipped" ? "Bu çalışmada atlandı" : step?.error || latestEvent?.message || (status === "done" ? "Tamamlandı" : statusLabel(status));
      return <div className={`live-step ${status}`} key={definition.key}>
        <span className="live-step-icon"><LiveStepIcon stepKey={definition.key} /></span>
        <div className="live-step-copy"><div><strong>{definition.title}</strong><b>{status === "skipped" ? "—" : `${progress}%`}</b></div><span>{detail}</span><div className="mini-meter"><i style={{ width: `${status === "skipped" ? 0 : progress}%` }} /></div></div>
      </div>;
    })}</div>
  </section>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric-card"><span>{label}</span><strong>{value}</strong></div>; }

function VariantSummary({ variants }: { variants: Variant[] }) {
  const groups = useMemo(() => {
    const map = new Map<string, Variant[]>();
    variants.forEach((item) => {
      const key = `${item.kind}|${item.size_label}|${item.orientation_label || ""}`;
      map.set(key, [...(map.get(key) || []), item]);
    });
    return Array.from(map.values());
  }, [variants]);
  return groups.length ? <div className="variant-list">{groups.slice(0, 40).map((rows) => <div className="variant-row" key={`${rows[0].kind}-${rows[0].size_label}-${rows[0].orientation_label}`}><span className={`kind-dot ${rows[0].kind}`} /><strong>{rows[0].size_label}</strong><span>{rows[0].kind === "framed" ? rows.map((item) => item.frame_label).filter(Boolean).join(", ") : rows[0].kind}</span><b>{money(Math.min(...rows.map((item) => item.sale_price_usd)))}</b></div>)}</div> : <EmptyState title="Varyasyon yok" text="Varsayılan CSV ayarlarını kontrol et." />;
}

type ExistingProps = {
  products: CatalogProduct[]; pagination: Pagination; search: string; loading: boolean; detail: CatalogProduct | null;
  detailTab: ExistingTab;
  remoteImages: Asset[]; remoteVideos: Asset[]; selections: Selection[]; selectionRoot: string; selectedSelection: string;
  editorOpen: boolean; mediaJob: MediaJob | null; selectedAssets: Set<string>; confirmation: string;
  artworkRef: React.RefObject<HTMLInputElement | null>;
  section: ExistingSection; sourceQueueItems: BulkMockupItem[]; readyQueueItems: BulkMockupItem[];
  bulkSelectMode: boolean; bulkSelectedIds: Set<string>; bulkSelectionName: string;
  sourceReviewItem: BulkMockupItem | null; readyReviewItem: BulkMockupItem | null;
  onSearchChange: (value: string) => void; onSearch: (event: FormEvent<HTMLFormElement>) => void; onPage: (page: number) => void;
  onRefresh: () => void; onOpen: (product: CatalogProduct) => void; onBack: () => void; onEditorOpen: () => void; onEditorClose: () => void;
  onDetailTab: (tab: ExistingTab) => void;
  onSelection: (value: string) => void; onPreview: (event: FormEvent<HTMLFormElement>) => void; onToggleAsset: (id: string) => void;
  onOpenSelection: (name: string) => void; onReloadSelections: () => void;
  onConfirmation: (value: string) => void; onApply: () => void; onPushVariants: () => void;
  onSection: (section: ExistingSection) => void; onToggleBulkMode: () => void;
  onToggleBulkProduct: (productId: string) => void; onBulkSelection: (value: string) => void; onStartBulk: () => void;
  onReviewSource: (itemId: string) => void;
  onReviewSourceAction: (item: BulkMockupItem, action: "approve" | "reject" | "hold") => void;
  onCloseSourceReview: () => void; onReviewReady: (itemId: string) => void;
  onApplyReady: (item: BulkMockupItem) => void; onCloseReadyReview: () => void;
  onPauseAll: () => void; onResumeAll: () => void;
  onPauseItem: (item: BulkMockupItem) => void; onResumeItem: (item: BulkMockupItem) => void;
  onReplaceSource: (item: BulkMockupItem, file: File) => void; onDeleteQueueItem: (item: BulkMockupItem) => void;
};

function ExistingProductsView(props: ExistingProps) {
  if (props.detail) return <ExistingProductDetail {...props} />;
  const sectionTabs = <nav className="existing-section-tabs">
    <button className={props.section === "catalog" ? "active" : ""} onClick={() => props.onSection("catalog")}><Grid2X2 /> Mevcut ürünler <b>{props.pagination.total}</b></button>
    <button className={props.section === "source" ? "active" : ""} onClick={() => props.onSection("source")}><Sparkles /> Ana ürünü seçilmiş ürünler <b>{props.sourceQueueItems.length}</b></button>
    <button className={props.section === "ready" ? "active" : ""} onClick={() => props.onSection("ready")}><PackageCheck /> Etsy’ye gönderilmeye hazır ürünler <b>{props.readyQueueItems.length}</b></button>
  </nav>;
  return <div className="view-stack existing-catalog-view">
    <header className="catalog-header">
      <div><span className="eyebrow">ETSY MAĞAZASI</span><h1>Mevcut ürün işlemleri</h1><p>Kaynağı onayla, Photoshop üretimini arka planda sürdür, hazır ürünü Etsy’ye göndermeden önce son kez incele.</p></div>
      <div className="header-actions">{props.section === "catalog" ? <button className={`button ${props.bulkSelectMode ? "primary" : ""}`} onClick={props.onToggleBulkMode}><Check /> {props.bulkSelectMode ? "Seçimi kapat" : "Toplu ürün seç"}</button> : null}<button className="button" onClick={props.onRefresh} disabled={props.loading}><RefreshCw /> Etsy’den yenile</button></div>
    </header>
    {sectionTabs}
    {props.section === "catalog" ? <><section className="catalog-commandbar">
      <form className="catalog-search" onSubmit={props.onSearch}>
        <Search />
        <input value={props.search} onChange={(event) => props.onSearchChange(event.target.value)} placeholder="Ürün adı veya listing ID ara" />
        {props.search ? <button className="clear-search" type="button" aria-label="Aramayı temizle" onClick={() => props.onSearchChange("")}><X /></button> : null}
        <button className="button" type="submit">Ara</button>
      </form>
      <div className="catalog-count"><PackageCheck /><span><strong>{props.pagination.total}</strong> Etsy ürünü</span></div>
      <PaginationBar pagination={props.pagination} onPage={props.onPage} compact />
    </section>
    {props.bulkSelectMode ? <section className="bulk-selection-bar"><div><strong>{props.bulkSelectedIds.size} ürün seçildi</strong><span>Tek mockup klasörü tüm seçilen ürünlerde kullanılacak.</span></div><label>Mockup klasörü<select value={props.bulkSelectionName} onChange={(event) => props.onBulkSelection(event.target.value)}><option value="">Klasör seç</option>{props.selections.filter((item) => item.ready).map((item) => <option key={item.name} value={item.name}>{item.name} · {item.mockup_count} PSD</option>)}</select></label><button className="button primary large" disabled={!props.bulkSelectedIds.size || !props.bulkSelectionName || props.loading} onClick={props.onStartBulk}><Sparkles /> Toplu mockup üret</button></section> : null}
    {props.loading ? <Loading label="Bu sayfadaki dört ürün yükleniyor" /> : <div className="catalog-grid">{props.products.map((product) => <article className={`catalog-card ${props.bulkSelectedIds.has(product.id) ? "bulk-selected" : ""}`} key={product.id}>
      {props.bulkSelectMode ? <label className="catalog-selector"><input type="checkbox" checked={props.bulkSelectedIds.has(product.id)} onChange={() => props.onToggleBulkProduct(product.id)} /><span>{props.bulkSelectedIds.has(product.id) ? <Check /> : null}</span></label> : null}
      <button className="catalog-card-main" onClick={() => props.bulkSelectMode ? props.onToggleBulkProduct(product.id) : props.onOpen(product)}>
        <div className="catalog-image">{product.thumb_url ? <img src={product.thumb_url} alt={product.name} loading="lazy" /> : <div className="missing-media"><ImageIcon /><span>Görsel bulunamadı</span></div>}<span className="listing-chip">#{product.listing_id}</span>{product.selection_name ? <span className="selection-chip">{product.selection_name}</span> : null}</div>
        <div className="catalog-copy"><div><span className="listing-label">{product.selection_name || "ETSY LISTING"}</span><h2>{product.name}</h2></div><div className="catalog-meta"><span><Images />{product.image_count || 0} görsel</span><span><Film />{product.video_count || 0} video</span><span><ListFilter />{product.variant_count || 0} varyasyon</span></div><span className="open-link">{props.bulkSelectMode ? "Toplu işleme seç" : "Ürün çalışma alanını aç"} <ChevronRight /></span></div>
      </button>
    </article>)}</div>}
    {!props.loading && !props.products.length ? <EmptyState title="Ürün bulunamadı" text="Aramayı temizle veya Etsy’den yenile." /> : null}
    <PaginationBar pagination={props.pagination} onPage={props.onPage} /></> : null}
    {props.section === "source" ? <QueueSection title="Ana ürünü seçilmiş ürünler" text="Ana görsel onayı verilen ürünler sırayla Photoshop’ta üretilir. Panel kapansa bile sıra kalıcıdır." actions={<><button className="button danger" onClick={props.onPauseAll}><Pause /> Tümünü durdur</button><button className="button" onClick={props.onResumeAll}><Play /> Durdurulanları devam ettir</button></>}>
      {props.sourceQueueItems.length ? <div className="queue-product-grid">{props.sourceQueueItems.map((item) => <article className="queue-product-card" key={item.id}>
        <div className="queue-product-image">{item.extracted_url ? <img src={item.extracted_url} alt={item.product_name} /> : item.current_thumb_url ? <img src={item.current_thumb_url} alt={item.product_name} /> : <ImageIcon />}<span className={`queue-state ${item.status}`}>{bulkQueueStatus(item.status)}</span></div>
        <div><span className="listing-label">LISTING #{item.listing_id}</span><h3>{item.product_name}</h3><p>{item.selection_name}</p>{item.error ? <small className="queue-error">{item.error}</small> : null}</div>
        <div className="queue-card-footer">
          <span>{item.status === "producing" ? `${item.media_job?.progress || 0}%` : item.status === "awaiting_source_approval" ? `%${Math.round(item.confidence)} eşleşme` : bulkQueueStatus(item.status)}</span>
          <div className="queue-actions">
            {item.status === "awaiting_source_approval" ? <button className="button primary" onClick={() => props.onReviewSource(item.id)}>Ana görseli incele</button> : null}
            {["analyzing", "source_approved", "producing"].includes(item.status) ? <button className="icon-button" title="Durdur" onClick={() => props.onPauseItem(item)}><Pause /></button> : null}
            {["paused", "error"].includes(item.status) ? <button className="button" onClick={() => props.onResumeItem(item)}><RotateCcw /> Yeniden dene</button> : null}
            {!["applying", "done"].includes(item.status) ? <label className="button quiet file-button"><Upload /> Görsel değiştir<input type="file" accept="image/png,image/jpeg" onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              if (file) props.onReplaceSource(item, file);
              event.currentTarget.value = "";
            }} /></label> : null}
            <button className="icon-button danger-quiet" title="Listeden sil" onClick={() => props.onDeleteQueueItem(item)}><Trash2 /></button>
          </div>
        </div>
      </article>)}</div> : <EmptyState title="Bu alanda ürün yok" text="Mevcut ürünlerden seçim yapıp toplu mockup işlemini başlat." />}
    </QueueSection> : null}
    {props.section === "ready" ? <QueueSection title="Etsy’ye gönderilmeye hazır ürünler" text="Photoshop üretimi tamamlandı. Her ürünü ayrı inceleyip onaylamadan Etsy’ye hiçbir dosya gönderilmez.">
      {props.readyQueueItems.length ? <div className="queue-product-grid">{props.readyQueueItems.map((item) => {
        const preview = item.media_job?.preview?.images || [];
        const videoAction = item.media_job?.preview?.video_action;
        const videoText = videoAction === "create" ? "1 yeni video" : videoAction === "preserve" ? "mevcut video korunacak" : "video yok";
        return <article className="queue-product-card ready-card" key={item.id}><div className="queue-preview-strip">{preview.slice(0, 3).map((asset) => <img src={asset.url} alt={asset.label} key={asset.id} />)}</div><div><span className="listing-label">LISTING #{item.listing_id}</span><h3>{item.product_name}</h3><p>{preview.length} yeni görsel · {videoText} · varyasyonlar korunur</p>{item.error ? <small className="queue-error">{item.error}</small> : null}</div><div className="queue-card-footer"><span className={`queue-state ${item.status}`}>{bulkQueueStatus(item.status)}</span><div className="queue-actions"><button className="button primary" disabled={item.status !== "ready_to_send"} onClick={() => props.onReviewReady(item.id)}><PackageCheck /> İncele ve onayla</button><button className="icon-button danger-quiet" title="Listeden sil" onClick={() => props.onDeleteQueueItem(item)}><Trash2 /></button></div></div></article>;
      })}</div> : <EmptyState title="Hazır ürün yok" text="Onaylanan ürünlerin Photoshop üretimi tamamlandığında burada görünür." />}
    </QueueSection> : null}
    {props.sourceReviewItem ? <SourceReviewModal item={props.sourceReviewItem} onClose={props.onCloseSourceReview} onAction={props.onReviewSourceAction} /> : null}
    {props.readyReviewItem ? <ReadyReviewModal item={props.readyReviewItem} busy={props.loading} onClose={props.onCloseReadyReview} onApply={props.onApplyReady} /> : null}
  </div>;
}

function bulkQueueStatus(status: string) {
  return ({
    analyzing: "Ana görsel aranıyor",
    awaiting_source_approval: "Ana görsel onayı",
    source_approved: "Üretim sırasında",
    producing: "Photoshop çalışıyor",
    paused: "Durduruldu",
    ready_to_send: "Etsy onayı bekliyor",
    applying: "Etsy’ye aktarılıyor",
    done: "Tamamlandı",
    error: "Kontrol gerekli"
  } as Record<string, string>)[status] || status;
}

function QueueSection({ title, text, actions, children }: { title: string; text: string; actions?: React.ReactNode; children: React.ReactNode }) {
  return <section className="queue-section"><div className="section-heading"><div><span className="eyebrow">KALICI İŞ LİSTESİ</span><h2>{title}</h2><p>{text}</p></div>{actions ? <div className="queue-section-actions">{actions}</div> : null}</div>{children}</section>;
}

function SourceReviewModal({ item, onClose, onAction }: { item: BulkMockupItem; onClose: () => void; onAction: (item: BulkMockupItem, action: "approve" | "reject" | "hold") => void }) {
  return <div className="review-overlay"><section className="review-modal"><header><div><span className="eyebrow">ANA GÖRSEL ONAYI</span><h2>{item.product_name}</h2><p>Çerçeve içinden çıkarılan görseli kontrol et. Onaylanan ürün kalıcı üretim sırasına girer.</p></div><button className="icon-button" onClick={onClose}><X /></button></header><div className="source-review-grid"><figure><span>Etsy mockupı · sıra {item.source_rank}</span>{item.source_etsy_url ? <img src={item.source_etsy_url} alt="Etsy mockupı" /> : null}</figure><figure className="extracted-source"><span>Bulunan ana görsel · %{Math.round(item.confidence)} güven</span>{item.extracted_url ? <img src={item.extracted_url} alt="Çıkarılan ana görsel" /> : null}</figure></div><footer><button className="button" onClick={onClose}>Şimdilik beklet</button><button className="button danger-quiet" onClick={() => onAction(item, "reject")}><X /> İşlemden çıkar</button><button className="button primary large" onClick={() => onAction(item, "approve")}><Check /> Onayla ve üretim sırasına al</button></footer></section></div>;
}

function ReadyReviewModal({ item, busy, onClose, onApply }: { item: BulkMockupItem; busy: boolean; onClose: () => void; onApply: (item: BulkMockupItem) => void }) {
  const images = item.media_job?.preview?.images || [];
  const videos = item.media_job?.preview?.videos || [];
  const videoAction = item.media_job?.preview?.video_action;
  const videoText = videoAction === "create" ? "Eksik Etsy videosu üretildi ve aşağıda önizleniyor." : videoAction === "preserve" ? "Mevcut Etsy videosu aynen korunacak." : "Bu üründe video işlemi yok.";
  return <div className="review-overlay"><section className="review-modal ready-review"><header><div><span className="eyebrow">SON ETSY ONAYI</span><h2>{item.product_name}</h2><p>{images.length} görsel Etsy’ye gönderilecek. {videoText} Varyasyonlara dokunulmayacak.</p></div><button className="icon-button" onClick={onClose}><X /></button></header><div className="ready-review-grid">{images.map((asset, index) => <figure key={asset.id}><span>{index + 1}</span><img src={`${asset.url}?preview=1`} alt={asset.label} loading="lazy" decoding="async" /><figcaption>{asset.label}</figcaption></figure>)}{videos.map((asset) => <figure className="video-preview-card" key={asset.id}><span><Film /></span><video src={asset.url} controls muted /><figcaption>{asset.label} · Etsy videosu</figcaption></figure>)}</div><footer><button className="button" onClick={onClose}>Onaylamadan kapat</button><button className="button primary large" disabled={busy} onClick={() => onApply(item)}><CloudUpload /> Onayla ve Etsy’ye gönder</button></footer></section></div>;
}

function PaginationBar({ pagination, onPage, compact = false }: { pagination: Pagination; onPage: (page: number) => void; compact?: boolean }) {
  return <div className={`pagination ${compact ? "compact" : ""}`}><button aria-label="Önceki sayfa" disabled={pagination.page <= 1} onClick={() => onPage(pagination.page - 1)}><ChevronLeft /></button><span><strong>{pagination.page}</strong> / {pagination.total_pages}</span><button aria-label="Sonraki sayfa" disabled={pagination.page >= pagination.total_pages} onClick={() => onPage(pagination.page + 1)}><ChevronRight /></button></div>;
}

function ExistingProductDetail(props: ExistingProps) {
  const listing = props.detail?.etsy_listing || {};
  const primaryImage = props.remoteImages[0];
  return <div className="view-stack existing-detail-view">
    <button className="back-button" onClick={props.onBack}><ArrowLeft /> Mevcut ürünlere dön</button>
    <header className="listing-workspace-header">
      <div className="listing-title-block"><span className="listing-id-label">LISTING #{props.detail?.listing_id}</span><h1>{props.detail?.name || "Ürün"}</h1><div className="listing-status-line"><span className="state-badge">{String(listing.state || "Etsy ürünü")}</span>{props.detail?.selection_name ? <span className="state-badge selection-state">{props.detail.selection_name}</span> : null}<span>{props.remoteImages.length} görsel</span><span>{props.remoteVideos.length} video</span><span>{props.detail?.variants?.length || 0} varyasyon</span></div></div>
      <div className="header-actions"><a className="button" href={props.detail?.etsy_listing_url} target="_blank" rel="noreferrer"><ExternalLink /> Etsy’de aç</a><button className="button primary" onClick={props.onEditorOpen}><Sparkles /> Görselleri düzenle</button></div>
    </header>
    <div className="safety-banner"><ShieldCheck /><strong>Onay kontrolü açık</strong><span>Photoshop önizlemesi Etsy’ye yazmaz. Yalnızca açıkça seçip onayladığın medya ve varyasyonlar uygulanır.</span></div>
    <nav className="detail-tabs" aria-label="Ürün ayrıntıları">
      <DetailTab active={props.detailTab === "overview"} icon={<LayoutDashboard />} label="Genel bakış" onClick={() => props.onDetailTab("overview")} />
      <DetailTab active={props.detailTab === "media"} icon={<Images />} label="Medya" count={props.remoteImages.length + props.remoteVideos.length} onClick={() => props.onDetailTab("media")} />
      <DetailTab active={props.detailTab === "variants"} icon={<ListFilter />} label="Varyasyonlar" count={props.detail?.variants?.length || 0} onClick={() => props.onDetailTab("variants")} />
    </nav>
    {props.detailTab === "overview" ? <section className="overview-workspace">
      <div className="listing-hero-media">{primaryImage?.url ? <img src={primaryImage.url} alt={props.detail?.name || "Etsy ürünü"} /> : <div className="missing-media large"><ImageIcon /><span>Ana görsel bulunamadı</span></div>}<div className="media-strip">{props.remoteImages.slice(0, 6).map((asset) => <img key={asset.id} src={asset.url} alt={asset.label} loading="lazy" />)}{props.remoteImages.length > 6 ? <span>+{props.remoteImages.length - 6}</span> : null}</div></div>
      <aside className="listing-facts-panel"><div className="panel-title"><div><span className="eyebrow">ÜRÜN ÖZETİ</span><h2>Kontrol bilgileri</h2></div><PackageCheck /></div><Fact label="Durum" value={String(listing.state || "-")} /><Fact label="Selection" value={props.detail?.selection_name || "Etsy'den okunamadı"} /><Fact label="Listing ID" value={props.detail?.listing_id || "-"} /><Fact label="DigitalDownload SKU" value={props.detail?.digital_download_sku || "-"} /><Fact label="Varyasyon" value={`${props.detail?.variants?.length || 0} satır`} /><Fact label="Yerel ana görsel" value={props.detail?.has_local_source || props.detail?.source_image_path ? "Hazır" : "Seçilmesi gerekli"} /><div className="archive-note"><Archive /><div><strong>Digital teslim arşivi</strong><span>Onaylı güncellemeden sonra ana görsel “Güncel Etsy Ürünleri” klasörüne SKU adıyla kaydedilir.</span></div></div><button className="button primary full" onClick={props.onEditorOpen}><Sparkles /> Yeni medya hazırla</button></aside>
    </section> : null}
    {props.detailTab === "media" ? <section className="current-media-workspace"><div className="section-heading"><div><span className="eyebrow">ETSY’DE YAYINDA</span><h2>Mevcut görseller ve video</h2><p>Bu alan yalnızca Etsy’den okunan güncel medyayı gösterir.</p></div><button className="button primary" onClick={props.onEditorOpen}><Sparkles /> Görselleri düzenle</button></div><div className="media-grid detailed">{props.remoteImages.map((asset, index) => <figure key={asset.id}><div className="media-rank">{index + 1}</div><img src={asset.url} alt={asset.label} loading="lazy" /><figcaption>{asset.label}</figcaption></figure>)}</div>{props.remoteVideos.length ? <div className="video-section"><div><Film /><strong>Etsy videosu</strong></div>{props.remoteVideos.map((asset) => <video className="wide-video" key={asset.id} src={asset.url} controls />)}</div> : null}</section> : null}
    {props.detailTab === "variants" ? <section className="variants-workspace"><div className="section-heading"><div><span className="eyebrow">ETSY INVENTORY</span><h2>Gönderilecek varyasyonlar</h2><p>İstersen yalnızca varyasyonları şimdi gönder; görsel güncellemesini onayladığında da otomatik gönderilir.</p></div><div className="header-actions"><span className="count-badge">{props.detail?.variants?.length || 0} satır</span><button className="button primary" disabled={props.loading || !props.detail?.variants?.length} onClick={props.onPushVariants}><CloudUpload /> Varyasyonları Etsy'ye gönder</button></div></div><VariantSummary variants={props.detail?.variants || []} /></section> : null}
    {props.editorOpen ? <MediaEditor {...props} /> : null}
  </div>;
}

function DetailTab(props: { active: boolean; icon: React.ReactNode; label: string; count?: number; onClick: () => void }) {
  return <button className={props.active ? "active" : ""} onClick={props.onClick}>{props.icon}<span>{props.label}</span>{props.count !== undefined ? <b>{props.count}</b> : null}</button>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="fact"><span>{label}</span><strong>{value}</strong></div>; }

function MediaEditor(props: ExistingProps) {
  const images = props.mediaJob?.preview?.images || [];
  const videos = props.mediaJob?.preview?.videos || [];
  const jobActive = props.mediaJob && ["queued", "running", "applying"].includes(props.mediaJob.status);
  const step = props.mediaJob?.status === "done" || props.mediaJob?.status === "applying" ? 3 : images.length ? 2 : 1;
  return <div className="media-workspace-overlay"><section className="media-workspace">
    <header className="media-workspace-header"><div><span className="eyebrow">GÜVENLİ MEDYA DEĞİŞİMİ</span><h2>{props.detail?.name}</h2><p>Selection seç, Photoshop çıktısını incele, sonra Etsy değişikliğini açıkça onayla.</p></div><button className="icon-button" aria-label="Kapat" onClick={props.onEditorClose}><X /></button></header>
    <aside className="media-step-rail">
      <WorkflowStep number={1} title="Selection" text="Şablon klasörünü seç" active={step === 1} done={step > 1} />
      <WorkflowStep number={2} title="Önizleme" text="Yeni medyayı kontrol et" active={step === 2} done={step > 2} />
      <WorkflowStep number={3} title="Etsy onayı" text="Yedekle ve uygula" active={step === 3} done={props.mediaJob?.status === "done"} />
      <div className="workspace-safety"><ShieldCheck /><span>Mevcut medya, yeni dosyalar doğrulanmadan kalıcı olarak bırakılmaz.</span></div>
    </aside>
    <main className="media-workspace-body">
      <section className="selection-stage"><div className="stage-heading"><div><span>1. ADIM</span><h3>Selection klasörünü seç</h3><p>Her klasör kendi PSD mockuplarını ve video şablonunu kullanır.</p></div><button className="button quiet" onClick={props.onReloadSelections}><RefreshCw /> Klasörleri yenile</button></div><div className="selection-root"><FolderOpen /><code>{props.selectionRoot}</code></div><div className="selection-grid">{props.selections.map((item) => <div className={`selection-card ${props.selectedSelection === item.name ? "selected" : ""} ${item.ready ? "" : "not-ready"}`} key={item.name}><button className="selection-main" type="button" disabled={!item.ready} onClick={() => props.onSelection(item.name)}><span className="selection-check">{props.selectedSelection === item.name ? <Check /> : <span />}</span><strong>{item.name}</strong><small>{item.ready ? `${item.mockup_count} mockup · ${item.video_count} video` : "PSD bekleniyor"}</small></button><button className="open-folder-button" type="button" title="Klasörü aç" aria-label={`${item.name} klasörünü aç`} onClick={() => props.onOpenSelection(item.name)}><FolderOpen /></button></div>)}</div></section>
      <form className="source-stage" onSubmit={props.onPreview}><div className="stage-heading"><div><span>PHOTOSHOP KAYNAĞI</span><h3>Orijinal tasarımı belirle</h3><p>Yerel ana görsel hazırsa dosya seçmeden devam edebilirsin.</p></div></div><label className="artwork-drop"><Upload /><strong>Orijinal ana görsel</strong><span>PNG veya JPG seç</span><input ref={props.artworkRef} type="file" accept="image/*" /></label><div className="workspace-safety"><ShieldCheck /><span>Etsy videosu varsa aynen korunur; yoksa selection klasöründen otomatik oluşturulur.</span></div><button className="button primary large" disabled={Boolean(jobActive) || !props.selectedSelection}><Sparkles /> {jobActive ? "Photoshop çalışıyor..." : "Photoshop önizlemesini üret"}</button></form>
      {props.mediaJob ? <div className={`job-status-box ${props.mediaJob.status}`}><div><strong>{props.mediaJob.stage}</strong><span>{statusLabel(props.mediaJob.status)}</span></div><b>{props.mediaJob.progress}%</b><div className="large-meter"><i style={{ width: `${props.mediaJob.progress}%` }} /></div>{props.mediaJob.error ? <p><CircleAlert />{props.mediaJob.error}</p> : null}</div> : null}
      {images.length ? <section className="preview-stage"><div className="stage-heading"><div><span>2. ADIM</span><h3>Yeni Etsy önizlemesi</h3><p>{props.selectedAssets.size} dosya seçili. Mockupları kapatabilirsin; ana görsel, bilgi görselleri ve gerekiyorsa yeni video zorunludur.</p></div></div><div className="preview-comparison"><div className="current-preview-column"><span>ŞU AN ETSY’DE</span><div className="current-preview-stack">{props.remoteImages.slice(0, 4).map((asset) => <img key={asset.id} src={asset.url} alt={asset.label} />)}</div></div><div className="new-preview-column"><span>YENİ ÖNİZLEME</span><div className="media-grid selectable">{images.map((asset) => <label className={`${props.selectedAssets.has(asset.id) ? "selected" : ""} ${asset.protected || asset.required ? "protected-media" : ""}`} key={asset.id}><input type="checkbox" checked={props.selectedAssets.has(asset.id)} disabled={asset.protected || asset.required} onChange={() => props.onToggleAsset(asset.id)} /><img src={`${asset.url}?preview=1`} alt={asset.label} loading="lazy" decoding="async" /><span>{asset.label}{asset.protected || asset.required ? <b><ShieldCheck /> Zorunlu</b> : null}</span></label>)}{videos.map((asset) => <label className={`video-select ${props.selectedAssets.has(asset.id) ? "selected" : ""} ${asset.required ? "protected-media" : ""}`} key={asset.id}><input type="checkbox" checked={props.selectedAssets.has(asset.id)} disabled={asset.required} onChange={() => props.onToggleAsset(asset.id)} /><video src={asset.url} controls muted /><span>{asset.label}{asset.required ? <b><ShieldCheck /> Otomatik video</b> : null}</span></label>)}</div></div></div></section> : null}
      {props.mediaJob?.status === "ready" ? <section className="approval-box"><div className="approval-copy"><ShieldCheck /><div><span>3. ADIM</span><h3>Doğrula ve doğrudan uygula</h3><p>Onayladığın yeni medya Etsy’ye yüklenir, doğrulanır ve eski görseller kaldırılır. Paneldeki varyasyonlar aynı ürüne gönderilir.</p></div></div><label className="field danger-field">Onay metni<input value={props.confirmation} onChange={(event) => props.onConfirmation(event.target.value)} placeholder={props.mediaJob.confirmation_text} /><small>Tam olarak <code>{props.mediaJob.confirmation_text}</code> yaz.</small></label><button className="button danger large" disabled={props.confirmation !== props.mediaJob.confirmation_text || !props.selectedAssets.size} onClick={props.onApply}><PackageCheck /> Medya ve varyasyonları Etsy’de güncelle</button></section> : null}
      {props.mediaJob?.status === "done" ? <div className="completion-box"><Check /><div><strong>Güncelleme tamamlandı</strong><span>Etsy medyası doğrulandı; DigitalDownload ana görseli masaüstüne SKU adıyla kaydedildi.</span></div></div> : null}
    </main>
  </section></div>;
}

function WorkflowStep(props: { number: number; title: string; text: string; active: boolean; done?: boolean }) {
  return <div className={`workflow-step ${props.active ? "active" : ""} ${props.done ? "done" : ""}`}><span>{props.done ? <Check /> : props.number}</span><div><strong>{props.title}</strong><small>{props.text}</small></div></div>;
}

function SettingsView(props: { settings: Settings; busy: boolean; unframedRef: React.RefObject<HTMLInputElement | null>; framedRef: React.RefObject<HTMLInputElement | null>; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  return <div className="view-stack settings-view"><PageHeader eyebrow="SİSTEM" title="Gelişmiş ayarlar" text="Ürünlerin tamamında kullanılacak fiyat, CSV, Etsy ve güvenlik varsayılanları." />
    <form className="settings-panel" onSubmit={props.onSubmit}>
      <div className="settings-group"><div><h2>Fiyat ve varyasyon</h2><p>Buradaki CSV dosyaları yeni ürünlere otomatik uygulanır.</p></div><div className="settings-grid"><label className="field">Fiyat hesabı<select name="pricing_formula" defaultValue={props.settings.pricing_formula}><option value="margin">Kâr marjı · maliyet / (1 − oran)</option><option value="markup">Maliyete yüzde ekle</option><option value="fixed_size_table">Eski sabit fiyat tablosu</option></select></label><label className="field">Unframed CSV<input ref={props.unframedRef} type="file" accept=".csv,text/csv" /><small>{props.settings.default_unframed_csv_name || "Dosya seçilmedi"}</small></label><label className="field">Unframed kâr %<input name="default_unframed_percent" type="number" min="0" max="95" defaultValue={props.settings.default_unframed_percent} /></label><label className="field">Framed CSV<input ref={props.framedRef} type="file" accept=".csv,text/csv" /><small>{props.settings.default_framed_csv_name || "Dosya seçilmedi"}</small></label><label className="field">Framed kâr %<input name="default_framed_percent" type="number" min="0" max="95" defaultValue={props.settings.default_framed_percent} /></label><label className="field">Gelato fiyat çarpanı<input name="gelato_retail_multiplier" type="number" min="0.01" step="0.0001" defaultValue={props.settings.gelato_retail_multiplier} /></label><label className="toggle-field"><input name="include_shipping_in_profit" type="checkbox" defaultChecked={props.settings.include_shipping_in_profit} /><span>Kargoyu kâr hesabına dahil et</span></label></div></div>
      <div className="settings-group"><div><h2>Etsy varsayılanları</h2><p>Yeni listing oluştururken kullanılır.</p></div><div className="settings-grid"><label className="field">Etsy modu<select name="etsy_mode" defaultValue={props.settings.etsy_mode}><option value="draft">Draft</option><option value="dry_run">Dry run</option></select></label><label className="field">Varsayılan stok<input name="default_quantity" type="number" min="1" defaultValue={props.settings.default_quantity} /></label><label className="field">Shipping profile<input name="required_shipping_profile_name" defaultValue={props.settings.required_shipping_profile_name} /></label><label className="field">Production partner<input name="required_production_partner_name" defaultValue={props.settings.required_production_partner_name} /></label></div></div>
      <div className="settings-group"><div><h2>Bu bilgisayar</h2><p>Photoshop otomatik bulunur. Selection klasörünü laptopunuzdaki PSD klasörüne ayarlayın.</p></div><div className="settings-grid"><label className="field">Mockup Smart Object katman adı<input name="smart_object_layer" defaultValue={props.settings.smart_object_layer || "Kare 1"}/><small>PSD içindeki değiştirilecek akıllı nesnenin adı.</small></label><label className="field">Photoshop uygulaması<input name="photoshop_exe_path" defaultValue={props.settings.photoshop_exe_path} placeholder="Photoshop.exe yolu" /></label><label className="field">Selection klasörleri<input name="selection_mockup_root" defaultValue={props.settings.selection_mockup_root} placeholder="templates/Selections" /></label></div></div>
      <div className="settings-group"><div><h2>Etsy bağlantısı</h2><p>Uygulama anahtarlarını kaydettikten sonra Etsy hesabınıza izin verin. Bilgiler yalnızca bu bilgisayarda saklanır.</p></div><div className="settings-grid"><label className="field">Etsy Keystring<input name="etsy_keystring" autoComplete="off" placeholder={props.settings.secret_status?.etsy_keystring ? "Kayıtlı" : "Etsy uygulama anahtarı"} /></label><label className="field">Etsy Shared Secret<input name="etsy_shared_secret" type="password" autoComplete="new-password" placeholder={props.settings.secret_status?.etsy_shared_secret ? "Kayıtlı" : "Etsy uygulama gizli anahtarı"} /></label><a className="button" href="/api/etsy/oauth/start" onClick={async (event) => { event.preventDefault(); try { const data = await api<{ authorize_url: string }>("/api/etsy/oauth/start"); window.open(data.authorize_url, "etsy-oauth", "width=720,height=820"); } catch (error) { alert(error instanceof Error ? error.message : String(error)); } }}><ExternalLink /> Etsy hesabını bağla</a></div></div>
      <div className="settings-group"><div><h2>Güvenlik</h2><p>Mevcut Etsy ürünleri normal üretim butonlarından değiştirilemez.</p></div><div className="settings-grid"><label className="field">Medya yazma politikası<select name="etsy_media_write_policy" defaultValue={props.settings.etsy_media_write_policy}><option value="new_drafts_only">Sadece yeni draft</option><option value="disabled">Tüm medya yazmayı kapat</option></select></label><label className="toggle-field"><input name="auto_resume_queue_on_start" type="checkbox" defaultChecked={props.settings.auto_resume_queue_on_start} /><span>Sunucu açılınca yarım kuyruğu sürdür</span></label><div className="path-box"><span>Selection klasörleri</span><code>{props.settings.selection_mockup_root || "templates/Selections"}</code></div></div></div>
      <div className="settings-actions"><button className="button primary large" disabled={props.busy}>{props.busy ? "Kaydediliyor..." : "Ayarları kaydet"}</button></div>
    </form>
  </div>;
}

function Loading({ label }: { label: string }) { return <div className="loading-state"><span className="spinner" /><strong>{label}</strong></div>; }
function EmptyState({ title, text }: { title: string; text: string }) { return <div className="empty-state"><strong>{title}</strong><span>{text}</span></div>; }
