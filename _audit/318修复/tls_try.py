"""尝试多种浏览器启动参数，判断 TLS 握手失败是否可用参数规避。"""
import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
URL="https://gboqrz.hmf0d-gnako-vspyqi.work/topic/231872.html"
COMBOS=[
 ("chrome", ["--ignore-certificate-errors"], False),
 ("chrome", ["--ignore-certificate-errors","--disable-http2"], True),
 ("msedge", ["--ignore-certificate-errors"], True),
 ("chrome", ["--ignore-certificate-errors","--disable-features=TLS13"], True),
]
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        for ch,args,ignore in COMBOS:
            try:
                b=await pw.chromium.launch(channel=ch, headless=True, args=args)
            except Exception as e:
                print(ch,args,"launch失败",str(e)[:60]); continue
            ctx=await b.new_context(ignore_https_errors=ignore)
            p=await ctx.new_page()
            try:
                await p.goto(URL, wait_until="domcontentloaded", timeout=25000)
                t=await p.locator("body").inner_text()
                print(f"OK {ch} {args} ignore={ignore} 长度={len(t)} 含322={'322期' in t}")
            except Exception as e:
                print(f"ERR {ch} {args} ignore={ignore} {str(e).splitlines()[0][:70]}")
            await b.close()
asyncio.run(main())
