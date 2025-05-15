import { chromium, Page } from "playwright";
import { exit } from "process";

function wait(seconds: number, msg = ""): Promise<void> {
  if (msg) console.log(`[WAIT] ${msg} (${seconds}s)`);
  return new Promise((res) => setTimeout(res, seconds * 1000));
}

function normalizeText(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toUpperCase()
    .trim()
    .replace(/\s+/g, " ");
}

async function autocompleteSelect(page: Page, selector: string, value: string) {
  await page.click(selector);
  await wait(0.5);
  await page.fill(selector, value);
  await wait(1.2);
  await page.keyboard.press("ArrowDown");
  await wait(0.3);
  await page.keyboard.press("Enter");
  await wait(1);
}

async function ensureAutocompleteSelected(
  page: Page,
  selector: string,
  expectedValue: string,
  label: string,
  maxRetries = 2
): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    await autocompleteSelect(page, selector, expectedValue);
    const actual = (await page.inputValue(selector)).trim().toUpperCase();
    console.log(`[DEBUG] Verifying ${label}: attempt ${i + 1} → '${actual}'`);
    if (actual.includes(expectedValue.toUpperCase())) return;
    console.warn(`[WARNING] ${label} value not correctly applied, retrying...`);
  }
  throw new Error(
    `Failed to select ${label} correctly after ${maxRetries} attempts.`
  );
}

async function ensureNumberFilled(
  page: Page,
  selector: string,
  value: string
): Promise<void> {
  await page.fill(selector, value);
  await wait(0.5);
  const filled = (await page.inputValue(selector)).trim();
  if (filled !== value.trim()) {
    throw new Error(
      `Number field not filled correctly: expected '${value}', got '${filled}'`
    );
  }
}

async function getPostalCode(
  commune: string,
  street: string,
  number: string
): Promise<{ postalCode?: string; error?: string }> {
  console.log(
    `[INFO] Lookup started for commune='${commune}', street='${street}', number='${number}'`
  );

  const normalizedCommune = normalizeText(commune);
  const normalizedStreet = normalizeText(street);
  const normalizedNumber = normalizeText(number);

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.setDefaultTimeout(20000);

  try {
    console.log("[INFO] Navigating to Correos de Chile postal code page...");
    await page.goto("https://www.correos.cl/codigo-postal", {
      timeout: 30000,
      waitUntil: "domcontentloaded",
    });

    await page.waitForSelector("input#mini-search-form-text");
    await wait(1);

    console.log("[INFO] Selecting commune with verification...");
    await ensureAutocompleteSelected(
      page,
      "input#mini-search-form-text",
      normalizedCommune,
      "commune"
    );

    console.log("[INFO] Selecting street with verification...");
    await ensureAutocompleteSelected(
      page,
      "input#mini-search-form-text-direcciones",
      normalizedStreet,
      "street"
    );

    console.log("[INFO] Filling number with verification...");
    await ensureNumberFilled(
      page,
      "#_cl_cch_codigopostal_portlet_CodigoPostalPortlet_INSTANCE_MloJQpiDsCw9_numero",
      normalizedNumber
    );

    console.log("[INFO] Triggering form validation by clicking outside...");
    await page.click("label[for='mini-search-form-text']", { force: true });
    await wait(1);

    const searchBtn = page.locator(
      "#_cl_cch_codigopostal_portlet_CodigoPostalPortlet_INSTANCE_MloJQpiDsCw9_searchDirection"
    );
    console.log("[INFO] Waiting for 'Search' button to be enabled...");
    for (let i = 0; i < 20; i++) {
      const isEnabled = await searchBtn.isEnabled();
      if (isEnabled) break;
      await wait(0.5);
      if (i === 19)
        throw new Error("Search button did not become enabled in time.");
    }

    console.log("[INFO] Clicking 'Search'...");
    await searchBtn.click({ force: true });
    await wait(2);

    console.log("[INFO] Waiting for postal code result...");
    const resultLocator = page.locator(
      "#_cl_cch_codigopostal_portlet_CodigoPostalPortlet_INSTANCE_MloJQpiDsCw9_ddCodPostal"
    );
    await resultLocator.waitFor({ state: "visible", timeout: 15000 });

    const code = (await resultLocator.innerText()).trim();
    console.log(`[INFO] Postal code retrieved: ${code}`);
    return { postalCode: code };
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    console.error("[ERROR] Scraper failed:", message);
    try {
      await page.screenshot({ path: "error.png" });
      console.log("[DEBUG] Screenshot saved as error.png");
    } catch (ssErr) {
      console.warn("[WARNING] Could not capture screenshot:", ssErr);
    }
    return { error: `Scraper failed: ${message}` };
  } finally {
    console.log("[INFO] Closing browser...");
    await browser.close();
  }
}

// CLI entrypoint
(async () => {
  const [commune, street, number] = process.argv.slice(2);
  if (!commune || !street || !number) {
    console.error(
      JSON.stringify({
        error:
          "Invalid arguments. Usage: tsx index.ts 'Commune' 'Street' 'Number'",
      })
    );
    exit(1);
  }

  const result = await getPostalCode(commune, street, number);
  console.log(JSON.stringify(result));
})();
