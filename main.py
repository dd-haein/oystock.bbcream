import asyncio
import re
import os
import requests
from playwright.async_api import async_playwright

# 시작 로그
print("🎬 [시스템 시작] 재고 확인 성공률 보정 버전을 실행합니다.")

TARGET_URL = os.environ.get("TARGET_URL")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

async def get_inventory():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        results = []
        try:
            print(f"🚀 {TARGET_URL} 접속 중...")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            # 보안 확인 및 초기 로딩 대기
            print("⏳ 안정적인 로딩을 위해 10초간 대기합니다...")
            await asyncio.sleep(10) 

            opt_btn_sel = 'button:has-text("선택"), button[class*="OptionSelector_btn-option"]'
            
            # 옵션 버튼 대기
            await page.wait_for_selector(opt_btn_sel, timeout=20000)
            await page.click(opt_btn_sel)
            
            # 목록 대기
            await page.wait_for_selector('li[class*="OptionSelector_option-item"]', state="visible", timeout=15000)
            
            options_count = await page.locator('li[class*="OptionSelector_option-item"]').count()
            print(f"📦 총 {options_count}개의 옵션 발견")

            for i in range(options_count):
                # 목록이 닫혔는지 체크
                if not await page.locator('li[class*="OptionSelector_option-item"]').first.is_visible():
                    await page.click(opt_btn_sel)
                    await asyncio.sleep(1.5)

                items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                target = items[i]
                
                opt_name = (await target.locator('span[class*="option-item-tit"]').inner_text()).strip()
                print(f"🔄 [{i+1}/{options_count}] {opt_name} 분석 중...")

                class_attr = await target.get_attribute("class") or ""
                if "is-soldout" in class_attr:
                    results.append(f"{opt_name} : 품절")
                    continue

                # --- 핵심 수정 부분: 클릭 후 대기 시간 강화 ---
                await target.click(force=True)
                
                # 수량 입력창이 나타날 때까지 최대 5초간 대기 (매우 중요)
                input_sel = 'input[data-qa-name="input-product-number"], input[class*="QuantityCounter_count"]'
                try:
                    # 입력창이 나타날 때까지 끈질기게 기다립니다.
                    await page.wait_for_selector(input_sel, timeout=5000)
                    input_field = page.locator(input_sel).first
                    
                    # 창이 떴어도 확실히 입력 가능할 때까지 0.5초 더 대기
                    await asyncio.sleep(0.5)
                    
                    await input_field.fill("999")
                    await page.keyboard.press("Enter")
                    
                    stock = "확인 불가"
                    try:
                        toast_sel = 'div[class*="Toast_toast-inner"]'
                        # 토스트 메시지도 조금 더 여유 있게 대기
                        await page.wait_for_selector(toast_sel, timeout=5000)
                        toast_text = await page.inner_text(toast_sel)
                        if "재고" in toast_text:
                            match = re.search(r'\d+', toast_text)
                            stock = f"재고 {match.group()}개"
                    except:
                        stock = "재고 999+ 예상"
                    
                    print(f"✅ {opt_name} : {stock}")
                    results.append(f"{opt_name} : {stock}")
                    
                    # 삭제 버튼 클릭 (다음 옵션 확인을 위해 비우기)
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]').first
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await asyncio.sleep(1) # 삭제 처리 대기
                        
                except Exception as e:
                    print(f"⚠️ {opt_name} 수량창 대기 중 타임아웃: {e}")
                    results.append(f"{opt_name} : 수량 확인 불가")
                    # 에러 시 드롭다운이 꼬이지 않게 Escape 한 번 눌러줌
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
