import asyncio
import re
import os
import requests
from playwright.async_api import async_playwright

print("🎬 [시스템 시작] 재시도 로직이 추가된 정밀 분석 버전을 실행합니다.")

TARGET_URL = os.environ.get("TARGET_URL")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

async def get_inventory():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        results = []
        try:
            print(f"🚀 접속 중: {TARGET_URL}")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(10) 

            opt_btn_sel = 'button:has-text("선택"), button[class*="OptionSelector_btn-option"]'
            await page.wait_for_selector(opt_btn_sel, timeout=20000)
            await page.click(opt_btn_sel)
            await page.wait_for_selector('li[class*="OptionSelector_option-item"]', state="visible", timeout=15000)
            
            options_count = await page.locator('li[class*="OptionSelector_option-item"]').count()
            print(f"📦 총 {options_count}개의 옵션 발견")

            for i in range(options_count):
                if not await page.locator('li[class*="OptionSelector_option-item"]').first.is_visible():
                    await page.click(opt_btn_sel)
                    await asyncio.sleep(2)

                items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                target = items[i]
                opt_name = (await target.locator('span[class*="option-item-tit"]').inner_text()).strip()
                print(f"🔄 [{i+1}/{options_count}] {opt_name} 분석 중...")

                class_attr = await target.get_attribute("class") or ""
                if "is-soldout" in class_attr:
                    results.append(f"{opt_name} : 품절")
                    continue

                # --- 보강된 클릭 로직 ---
                await target.scroll_into_view_if_needed() # 화면에 잘 보이게 스크롤
                await target.click(force=True)
                
                input_sel = 'input[data-qa-name="input-product-number"], input[class*="QuantityCounter_count"]'
                
                # 수량창 대기 및 재시도 (최대 2번 시도)
                input_field = None
                for attempt in range(2):
                    try:
                        await page.wait_for_selector(input_sel, timeout=4000)
                        input_field = page.locator(input_sel).first
                        break 
                    except:
                        if attempt == 0:
                            print(f"⚠️ {opt_name} 수량창 미발견, 재클릭 시도...")
                            await target.click(force=True)
                        else:
                            print(f"❌ {opt_name} 최종 수량창 확인 실패")

                if input_field and await input_field.is_visible():
                    await asyncio.sleep(0.5)
                    await input_field.fill("999")
                    await page.keyboard.press("Enter")
                    
                    stock = "확인 불가"
                    try:
                        toast_sel = 'div[class*="Toast_toast-inner"]'
                        await page.wait_for_selector(toast_sel, timeout=4000)
                        toast_text = await page.inner_text(toast_sel)
                        if "재고" in toast_text:
                            match = re.search(r'\d+', toast_text)
                            stock = f"재고 {match.group()}개"
                    except:
                        stock = "재고 999+ 예상"
                    
                    print(f"✅ {opt_name} : {stock}")
                    results.append(f"{opt_name} : {stock}")
                    
                    # 삭제 버튼 클릭 후 확실히 사라질 때까지 대기
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]').first
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await asyncio.sleep(1.5)
                else:
                    results.append(f"{opt_name} : 수량 확인 불가")
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(1)

            return results

        except Exception as e:
            print(f"🚨 에러 발생: {e}")
            return results if results else [f"에러: {str(e)}"]
        finally:
            await browser.close()

def send_slack(msg_list):
    if not msg_list or not SLACK_WEBHOOK_URL: return
    report = "\n".join([f"• {m}" for m in msg_list])
    payload = {"text": f"📊 *올리브영 실시간 재고 리포트*\n{report}"}
    requests.post(SLACK_WEBHOOK_URL, json=payload)

if __name__ == "__main__":
    final_results = asyncio.run(get_inventory())
    send_slack(final_results)
