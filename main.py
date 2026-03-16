import asyncio
import re
import os
import requests
from playwright.async_api import async_playwright

# --- 설정 (GitHub Secrets에서 가져옴) ---
TARGET_URL = os.environ.get("TARGET_URL")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

async def get_inventory():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        results = []
        try:
            print(f"🚀 {TARGET_URL} 접속 중...")
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)

            # 드롭다운 버튼 선택자
            opt_btn_selector = 'button:has-text("선택"), button[class*="OptionSelector_btn-option"]'
            
            # 1. 전체 개수 파악
            await page.click(opt_btn_selector)
            await page.wait_for_selector('li[class*="OptionSelector_option-item"]', timeout=10000)
            
            options_count = await page.locator('li[class*="OptionSelector_option-item"]').count()
            print(f"📦 총 {options_count}개의 옵션 발견")
            await page.keyboard.press("Escape") # 일단 닫기

            for i in range(options_count):
                print(f"🔄 [{i+1}/{options_count}] 작업 시작...")
                
                # 드롭다운 열기
                await page.click(opt_btn_selector)
                await page.wait_for_timeout(1000)

                # i번째 옵션 찾기
                items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                target = items[i]
                
                # 옵션명 추출
                opt_name = (await target.locator('span[class*="option-item-tit"]').inner_text()).strip()
                
                # 품절 체크
                class_attr = await target.get_attribute("class")
                if "is-soldout" in (class_attr or ""):
                    results.append(f"{opt_name} : 품절")
                    print(f"🚫 {opt_name} : 품절")
                    await page.keyboard.press("Escape")
                    continue

                # 2. 클릭 시도 (좌표가 안 잡히면 일반 클릭 시도)
                box = await target.bounding_box()
                if box and box['width'] > 0:
                    await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                else:
                    print(f"⚠️ {opt_name} 좌표 획득 실패, 강제 클릭 시도")
                    await target.click(force=True)
                
                await page.wait_for_timeout(1500)

                # 3. 수량 입력창 확인
                input_field = page.locator('input[data-qa-name="input-product-number"], input[class*="QuantityCounter_count"]').first
                if await input_field.is_visible():
                    await input_field.focus()
                    await input_field.fill("999")
                    await page.keyboard.press("Enter")
                    
                    stock = "확인 불가"
                    try:
                        toast_sel = 'div[class*="Toast_toast-inner"]'
                        # 토스트가 나타날 때까지 대기
                        await page.wait_for_selector(toast_sel, timeout=5000)
                        toast_text = await page.inner_text(toast_sel)
                        
                        if "재고" in toast_text:
                            match = re.search(r'\d+', toast_text)
                            stock = f"재고 {match.group()}개" if match else "확인됨"
                            print(f"✅ {opt_name} : {stock}")
                    except:
                        stock = "재고 999+ 예상"
                        print(f"ℹ️ {opt_name} : {stock} (토스트 미발생)")
                    
                    results.append(f"{opt_name} : {stock}")
                    
                    # 삭제 버튼 클릭
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]').first
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await page.wait_for_timeout(800)
                else:
                    print(f"❌ {opt_name} : 수량창 미발견")
                    results.append(f"{opt_name} : 수량창 미발견")
                    await page.keyboard.press("Escape")

            return results

        except Exception as e:
            print(f"🚨 중단됨: {e}")
            return results if results else [f"에러 발생: {str(e)}"]
        finally:
            await browser.close()

def send_slack(msg_list):
    if not msg_list:
        print("📝 전송할 리포트가 없습니다.")
        return
    
    if not SLACK_WEBHOOK_URL:
        print("⚠️ 슬랙 URL이 없습니다.")
        return

    report = "\n".join([f"• {m}" for m in msg_list])
    payload = {"text": f"📊 *올리브영 실시간 재고 리포트*\n{report}"}
    
    resp = requests.post(SLACK_WEBHOOK_URL, json=payload)
    print(f"📢 슬랙 전송 결과: {resp.status_code}")

if __name__ == "__main__":
    if not TARGET_URL:
        print("❌ TARGET_URL이 없습니다. Secrets를 확인하세요.")
    else:
        final_results = asyncio.run(get_inventory())
        send_slack(final_results)
