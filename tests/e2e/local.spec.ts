import { test, expect } from '@playwright/test';

// Requires the local demo seed and npm run dev:all. No live provider calls.
test('merchant signs in, saves a draft product, and previews it on a store subdomain', async ({page}) => {
  await page.goto('/login');
  await page.getByLabel('Email address').fill('owner@example.test');
  await page.getByLabel('Password', {exact:true}).fill('Local-Mshoppa-2026!');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Good to see you, Alex.'})).toBeVisible();
  await page.getByRole('link',{name:'Products',exact:true}).click();
  await page.getByRole('button',{name:'Add product',exact:true}).click();
  const name = `Browser test tote ${Date.now()}`;
  await page.getByLabel('Product name').fill(name);
  await page.getByLabel('Price · KES').fill('1250');
  await page.getByLabel('Available quantity').fill('4');
  await page.getByRole('button',{name:'Save draft'}).click();
  await expect(page.getByText(name,{exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByText(name,{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Store settings',exact:true}).click();
  await page.getByRole('button',{name:'Private preview'}).click();
  await expect(page).toHaveURL(/everyday-studio\.localhost:4203/);
  await expect(page.getByText('PRIVATE PREVIEW', {exact:false})).toBeVisible();
  await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
  await expect(page).not.toHaveURL(/preview=/);
});

test('unknown local storefront fails closed', async ({page}) => {
  await page.goto('http://unknown-business.localhost:4203');
  await expect(page.getByRole('heading',{name:'A good thing is on its way.'})).toBeVisible();
  await expect(page.getByText('Everyday Studio',{exact:true})).toHaveCount(0);
});

test('mobile login has no horizontal page overflow', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/login');
  await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('edit product with offer, multi-image thumbnails and full preview', async ({page}) => {
  await page.goto('/login');
  await page.getByLabel('Email address').fill('owner@example.test');
  await page.getByLabel('Password', {exact:true}).fill('Local-Mshoppa-2026!');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('link',{name:'Products',exact:true}).click();
  await expect(page.getByText('THE THINGS THAT MAKE YOU, YOU')).toHaveCount(0);
  await page.getByRole('button',{name:'Add product',exact:true}).click();
  const name = `Image widget test ${Date.now()}`;
  await page.getByLabel('Product name').fill(name);
  await page.getByRole('spinbutton',{name:'Price · KES',exact:true}).fill('10000');
  await page.getByRole('spinbutton',{name:/Offer price/}).fill('8000');
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64');
  await page.getByLabel('Upload product images').setInputFiles([{name:'front.png',mimeType:'image/png',buffer:png},{name:'back.png',mimeType:'image/png',buffer:png}]);
  await expect(page.locator('.product-image-card')).toHaveCount(2);
  await page.getByRole('button',{name:'Preview selected image front.png',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Image preview'})).toBeVisible();
  await page.getByRole('button',{name:'Next',exact:true}).click();
  await expect(page.getByRole('dialog').getByText('back.png',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Close image preview'}).click();
  await page.getByRole('button',{name:'Save draft',exact:true}).click();
  await expect(page.getByText('Product saved as a draft.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:`Edit ${name}`,exact:true}).click();
  await expect(page.locator('.product-image-card')).toHaveCount(2);
  await expect(page.getByRole('spinbutton',{name:/Offer price/})).toHaveValue('8000.00');
  await page.getByLabel('Product name').fill(name+' updated');
  await page.getByRole('spinbutton',{name:/Offer price/}).fill('');
  await page.getByRole('button',{name:'Remove image back.png',exact:true}).click();
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await page.reload();
  await page.getByRole('button',{name:`Edit ${name} updated`,exact:true}).click();
  await expect(page.locator('.product-image-card')).toHaveCount(1);
  await expect(page.getByRole('spinbutton',{name:/Offer price/})).toHaveValue('');
});
