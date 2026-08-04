import { expect, test } from "@playwright/test";

test("compares driver, passenger, and abstention outcomes", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /Driver, passenger/ })).toBeVisible();
  await expect(page.getByTestId("active-gene")).toHaveText("IL4R");
  await expect(page.getByTestId("active-verdict")).toHaveText("Driver");

  await page.getByTestId("gene-select-S100A8").click();
  await expect(page.getByTestId("active-gene")).toHaveText("S100A8");
  await expect(page.getByTestId("active-verdict")).toHaveText("Passenger");
  await expect(page.getByText("No disease-relevant rescue evidence identified")).toBeVisible();

  await page.getByTestId("gene-select-FLG").click();
  await expect(page.getByTestId("active-gene")).toHaveText("FLG");
  await expect(page.getByTestId("active-verdict")).toHaveText("Insufficient evidence");
});

test("shows an offline-safe result when API is unavailable", async ({ page }) => {
  await page.route("**/api/analyze", (route) => route.abort());
  await page.goto("/");
  await page.getByTestId("run-analysis").click();
  await expect(page.getByTestId("run-notice")).toHaveText(
    "Backend unavailable — showing verified offline demo",
  );
  await expect(page.getByTestId("active-gene")).toHaveText("IL4R");
});
