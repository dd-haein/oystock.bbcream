import asyncio
import re
import os
import requests
from playwright.async_api import async_playwright

# --- 설정 ---
TARGET_URL = os.environ.get("TARGET_URL")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

async def get_inventory():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        results = []
        try:
            print(f"🚀 {TARGET_URL} 접속 중...")
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)

            # 1. 전체 옵션 개수 파악을 위해 먼저 한번 클릭
            opt_btn_selector = 'button:has-text("선택"), button[class*="OptionSelector_btn-option"]'
            await page.click(opt_btn_selector)
            await page.wait_for_timeout(1000)
            
            options_count = await page.locator('li[class*="OptionSelector_option-item"]').count()
            print(f"📦 총 {options_count}개의 옵션 발견")
            
            # 드롭다운 닫기 (다시 루프 안에서 열기 위해)
            await page.keyboard.press("Escape")

            for i in range(options_count):
                # --- 매 루프마다 드롭다운을 새로 열어 요소 위치를 초기화 ---
                await page.click(opt_btn_selector)
                await page.wait_for_timeout(800)
                
                # 현재 순서의 옵션 타겟팅
                items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                if i >= len(items): break # 안전장치
                
                target = items[i]
                opt_name = (await target.locator('span[class*="option-item-tit"]').inner_text()).strip()

                # 품절 체크
                class_attr = await target.get_attribute("class")
                if "is-soldout" in class_attr:
                    results.append(f"{opt_name} : 품절")
                    print(f"🚫 {opt_name} : 품절")
                    await page.keyboard.press("Escape") # 드롭다운 닫기
                    continue

                # 좌표 클릭
                box = await target.bounding_box()
                if box:
                    await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                    await page.wait_for_timeout(1000)

                # 수량 입력 및 확인
                input_field = page.locator('input[data-qa-name="input-product-number"], input[class*="QuantityCounter_count"]').first
                if await input_field.is_visible():
                    await input_field.fill("999")
                    await page.keyboard.press("Enter")
                    
                    stock = "확인 불가"
                    try:
                        toast_sel = 'div[class*="Toast_toast-inner"]'
                        await page.wait_for_selector(toast_sel, timeout=4000)
                        toast_text = await page.inner_text(toast_sel)
                        
                        if "재고" in toast_text:
                            match = re.search(r'\d+', toast_text)
                            stock = f"재고 {match.group()}개" if match else "재고 확인됨"
                    except:
                        stock = "재고 999+ 예상"
                    
                    print(f"✅ {opt_name} : {stock}")
                    results.append(f"{opt_name} : {stock}")
                    
                    # 수량창 삭제 버튼 클릭 (초기화)
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]').first
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await page.wait_for_timeout(500)
                else:
                    results.append(f"{opt_name} : 입력창 미발견")
                    await page.keyboard.press("Escape")

            return results

        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            return results if results else [f"실행 중 오류 발생: {str(e)}"]
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
