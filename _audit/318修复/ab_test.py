"""A/B：默认启动参数 vs --ignore-certificate-errors，各 4 轮，判断失败是证书相关还是随机。"""
import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
URL="https://gboqrz.hmf0d-gnako-vspyqi.work/topic/231872.html"
async def run(label, args):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        for i in range(4):
            b=await pw.chromium.launch(channel="chrome", headless=True, args=args)
            p=await b.new_page()
            try:
                await p.goto(URL, wait_until="domcontentloaded", timeout=20000)
                t=await p.locator("body").inner_text()
                print(f"{label} #{i+1} OK 长度={len(t)}")
            except Exception as e:
                print(f"{label} #{i+1} ERR {str(e).splitlines()[0][:60]}")
            await b.close()
            await asyncio.sleep(3)
async def main():
    await run("默认", [])
    await run("忽略证书", ["--ignore-certificate-errors"])
asyncio.run(main())
