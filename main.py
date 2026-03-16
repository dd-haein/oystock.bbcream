import asyncio
import re
import os
import requests
from playwright.async_api import async_playwright

# --- 설정 ---
# 본인이 확인하고 싶은 올리브영 URL로 교체하세요
TARGET_URL = "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=GA230920247" 
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

async def get_inventory():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 실제 브라우저처럼 보이게 하기 위한 설정
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        results = []
        try:
            print(f"🚀 {TARGET_URL} 접속 중...")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000) # 안정적인 로딩을 위해 대기

            # 1. 옵션 드롭다운 클릭
            opt_btn = page.locator('button[class*="OptionSelector_btn-option"]')
            if await opt_btn.count() == 0:
                print("❌ 옵션 버튼을 찾을 수 없습니다. (단일 상품이거나 매진일 수 있음)")
                return ["해당 페이지에 선택 가능한 옵션 버튼이 없습니다."]

            await opt_btn.click()
            await page.wait_for_timeout(2000)

            # 2. 모든 옵션 요소 가져오기
            options = await page.locator('li[class*="OptionSelector_option-item"]').all()
            print(f"📦 총 {len(options)}개의 옵션 발견")
            
            for i in range(len(options)):
                items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                target = items[i]
                
                name_el = target.locator('span[class*="option-item-tit"]')
                opt_name = (await name_el.inner_text()).strip()

                class_attr = await target.get_attribute("class")
                if "is-soldout" in class_attr:
                    results.append(f"{opt_name} : 품절")
                    print(f"🚫 {opt_name} : 품절")
                    continue

                # 3. 좌표 기반 정밀 클릭
                box = await target.bounding_box()
                if box:
                    await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                    await page.wait_for_timeout(1500)

                # 4. 수량 입력 및 엔터
                input_sel = 'input[data-qa-name="input-product-number"], input[class*="QuantityCounter_count"]'
                input_field = page.locator(input_sel).first
                
                if await input_field.is_visible():
                    await input_field.fill("999")
                    await page.keyboard.press("Enter")
                    
                    stock = "확인 불가 (재고 999+)"
                    try:
                        toast_sel = 'div[class*="Toast_toast-inner"]'
                        # 토스트가 뜰 때까지 대기
                        await page.wait_for_selector(toast_sel, timeout=5000)
                        toast_text = await page.inner_text(toast_sel)
                        
                        if "재고" in toast_text:
                            match = re.search(r'\d+', toast_text)
                            if match:
                                stock = f"재고 {match.group()}개"
                    except:
                        pass 
                    
                    res_msg = f"{opt_name} : {stock}"
                    print(f"✅ {res_msg}")
                    results.append(res_msg)
                    
                    # 삭제 버튼 클릭하여 초기화
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]')
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await page.wait_for_timeout(1000)
                else:
                    results.append(f"{opt_name} : 수량창 미발견")

            return results

        except Exception as e:
            print(f"❌ 실행 중 오류 발생: {e}")
            return [f"오류 발생: {str(e)}"]
        finally:
            await browser.close()

def send_slack(msg_list):
    if not msg_list:
        print("📝 보낼 결과가 없어 슬랙을 전송하지 않습니다.")
        return
    
    if not SLACK_WEBHOOK_URL:
        print("⚠️ SLACK_WEBHOOK_URL이 설정되지 않았습니다. Secrets 설정을 확인하세요.")
        return

    report = "\n".join([f"• {m}" for m in msg_list])
    payload = {"text": f"📊 *올리브영 실시간 재고 리포트*\n{report}"}
    
    response = requests.post(SLACK_WEBHOOK_URL, json=payload)
    if response.status_code == 200:
        print("🚀 슬랙 알림 전송 성공!")
    else:
        print(f"❌ 슬랙 전송 실패 (상태 코드: {response.status_code})")

if __name__ == "__main__":
    final_results = asyncio.run(get_inventory())
    send_slack(final_results)
