import { test, expect, type Page } from "@playwright/test";

/** Read the cash balance shown in the header. */
async function readCash(page: Page): Promise<number> {
  const text = await page.locator("header").innerText();
  const match = text.match(/Cash\s+\$([\d,]+\.\d{2})/);
  return match ? parseFloat(match[1].replace(/,/g, "")) : NaN;
}

/** Return the positions table row for a ticker. */
function positionRow(page: Page, ticker: string) {
  const panel = page.getByRole("heading", { name: "Positions" }).locator("..");
  return panel.locator("tr", {
    has: page.locator("td:first-child", { hasText: new RegExp(`^${ticker}$`) }),
  });
}

/** Read the held quantity for a ticker, 0 when no position is shown. */
async function readQty(page: Page, ticker: string): Promise<number> {
  const row = positionRow(page, ticker);
  if ((await row.count()) === 0) return 0;
  return parseFloat(await row.locator("td").nth(1).innerText());
}

/** Load the app and wait until prices stream and the portfolio has loaded. */
async function openLoaded(page: Page) {
  await page.goto("/");
  await expect(page.getByText("connected")).toBeVisible({ timeout: 10_000 });
  await expect.poll(() => readCash(page), { timeout: 10_000 }).toBeGreaterThan(0);
}

/** Submit a trade via the trade bar and return the fill price from the status. */
async function trade(page: Page, side: "buy" | "sell", ticker: string, qty: number) {
  await page.getByPlaceholder("Ticker", { exact: true }).fill(ticker);
  await page.getByPlaceholder("Qty").fill(String(qty));
  await page.getByRole("button", { name: side.toUpperCase(), exact: true }).click();
  const status = page.getByText(
    new RegExp(`^${side.toUpperCase()} ${qty} ${ticker} @ \\$[\\d.]+$`)
  );
  await expect(status).toBeVisible({ timeout: 5_000 });
  const match = (await status.innerText()).match(/\$([\d.]+)$/);
  return parseFloat(match![1]);
}

test.describe("Fresh start", () => {
  test("shows default watchlist and $10k balance", async ({ page }) => {
    await page.goto("/");
    // Header shows default portfolio value and cash
    await expect(page.getByText("$10,000.00").first()).toBeVisible();
    // App title renders
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "FinAlly"
    );
  });

  test("prices are streaming via SSE", async ({ page }) => {
    await page.goto("/");
    // Wait for connection status to show connected
    await expect(page.getByText("connected")).toBeVisible({ timeout: 10_000 });
    // At least one ticker should show a numeric price
    await expect(page.locator("td.tabular-nums").first()).not.toHaveText("--", {
      timeout: 10_000,
    });
  });
});

test.describe("Watchlist CRUD", () => {
  test("add and remove a ticker", async ({ page }) => {
    await page.goto("/");

    // Add a ticker
    const input = page.getByPlaceholder("Add ticker");
    await input.fill("SNAP");
    await input.press("Enter");
    await expect(page.getByText("SNAP")).toBeVisible({ timeout: 5_000 });

    // Remove the ticker
    const snapRow = page.locator("tr", { hasText: "SNAP" });
    await snapRow.getByTitle("Remove").click();
    await expect(page.getByText("SNAP")).not.toBeVisible({ timeout: 5_000 });
  });
});

test.describe("Trading", () => {
  test("buy shares: cash decreases and position appears", async ({ page }) => {
    await openLoaded(page);
    const cashBefore = await readCash(page);
    const qtyBefore = await readQty(page, "GOOGL");

    const price = await trade(page, "buy", "GOOGL", 2);

    await expect.poll(() => readCash(page)).toBeCloseTo(cashBefore - 2 * price, 1);
    await expect(positionRow(page, "GOOGL")).toBeVisible();
    await expect.poll(() => readQty(page, "GOOGL")).toBe(qtyBefore + 2);
  });

  test("sell shares: cash increases and position updates", async ({ page }) => {
    await openLoaded(page);
    const cashStart = await readCash(page);
    const buyPrice = await trade(page, "buy", "JPM", 2);
    await expect.poll(() => readCash(page)).toBeCloseTo(cashStart - 2 * buyPrice, 1);
    const held = await readQty(page, "JPM");
    const cashBefore = await readCash(page);

    // Partial sell: cash rises by proceeds, position quantity drops
    const price = await trade(page, "sell", "JPM", 1);
    await expect.poll(() => readCash(page)).toBeCloseTo(cashBefore + price, 1);
    await expect.poll(() => readQty(page, "JPM")).toBe(held - 1);

    // Sell the rest: position disappears
    await trade(page, "sell", "JPM", held - 1);
    await expect(positionRow(page, "JPM")).toHaveCount(0);
  });
});

test.describe("Portfolio visualization", () => {
  test("heatmap panel renders", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Portfolio Heatmap")).toBeVisible();
  });

  test("P&L panel renders", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("P&L")).toBeVisible();
  });
});

test.describe("AI Chat", () => {
  test("send a message and get a response", async ({ page }) => {
    await page.goto("/");

    // Chat panel should be visible
    await expect(page.getByText("AI Chat")).toBeVisible();

    // Empty state message
    await expect(
      page.getByText("Ask about stocks, trade, or manage your watchlist.")
    ).toBeVisible();

    // Type and send a message
    const chatInput = page.getByPlaceholder("Message...");
    await chatInput.fill("What stocks should I buy?");
    await page.getByRole("button", { name: "Send" }).click();

    // User message should appear
    await expect(
      page.getByText("What stocks should I buy?")
    ).toBeVisible();

    // Wait for assistant response (mocked or real)
    await expect(
      page.locator(".bg-bg-secondary.text-text-primary").first()
    ).toBeVisible({ timeout: 15_000 });
  });

  test("chat panel collapses and expands", async ({ page }) => {
    await page.goto("/");

    // Collapse
    await page.getByLabel("Collapse chat").click();
    await expect(page.getByText("AI Chat")).not.toBeVisible();

    // Expand
    await page.getByLabel("Expand chat").click();
    await expect(page.getByText("AI Chat")).toBeVisible();
  });
});

test.describe("SSE resilience", () => {
  test("reconnects after disconnect", async ({ page }) => {
    await page.goto("/");
    // Wait for initial connection
    await expect(page.getByText("connected")).toBeVisible({ timeout: 10_000 });

    // Simulate disconnect by blocking the SSE endpoint
    await page.route("**/api/stream/prices", (route) => route.abort());

    // Should show reconnecting
    await expect(page.getByText("reconnecting")).toBeVisible({
      timeout: 10_000,
    });

    // Restore the route
    await page.unroute("**/api/stream/prices");

    // Should reconnect
    await expect(page.getByText("connected")).toBeVisible({ timeout: 15_000 });
  });
});
