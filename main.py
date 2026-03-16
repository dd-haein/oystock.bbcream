import asyncio
import re
import os
import requests
import json
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from playwright.async_api import async_playwright

# --- 구글 시트 설정 ---
def update_google_sheet(data_dict):
    try:
        # GitHub Secrets에서 서비스 계정 JSON 가져오기
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
        if not creds_json:
            print("❌ 구글 시트 인증 정보가 없습니다.")
            return

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # 시트 열기 (URL 기반)
        sheet_url = "https://docs.google.com/spreadsheets/d/1Ij3YEV2rcVr6L3xHlZ_fDvOxXtMAOHtpjQCLNyVivmU/edit"
        doc = client.open_by_url(sheet_url)
        worksheet = doc.get_worksheet(0) # 첫 번째 탭

        # 날짜와 시간 준비 (한국 시간 기준은 +9시간 필요할 수 있음)
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        # 시트에 한 줄씩 추가
        # 행 구조: 날짜 | 시간 | 옵션명 | 재고수량
        new_rows = []
        for opt_name, stock_val in data_dict.items():
            # "재고 72개" -> 72 / "품절" -> 0 숫자로 변환
            num_stock = 0
            if "재고" in stock_val:
                match = re.search(r'\d+', stock_val)
                num_stock = int(match.group()) if match else 999
            
            new_rows.append([date_str, time_str, opt_name, num_stock])
        
        worksheet.append_rows(new_rows)
        print("📊 구글 시트 데이터 기록 완료!")
    except Exception as e:
        print(f"❌ 구글 시트 업데이트 에러: {e}")

# --- 재고 체크 메인 로직 ---
async def get_inventory():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 1024})
        page = await context.new_page()
        
        inventory_data = {} # 시트 기록용 딕셔너리
        slack_results = []
        
        try:
            await page.goto(os.environ.get("TARGET_URL"), wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(10)

            opt_btn_sel = 'button:has-text("선택"), button[class*="OptionSelector_btn-option"]'
            await page.wait_for_selector(opt_btn_sel)
            await page.click(opt_btn_sel)
            await page.wait_for_selector('li[class*="OptionSelector_option-item"]', state="visible")
            
            options_count = await page.locator('li[class*="OptionSelector_option-item"]').count()

            for i in range(options_count):
                if not await page.locator('li[class*="OptionSelector_option-item"]').first.is_visible():
                    await page.click(opt_btn_sel)
                    await asyncio.sleep(2)

                items = await page.locator('li[class*="OptionSelector_option-item"]').all()
                target = items[i]
                opt_name = (await target.locator('span[class*="option-item-tit"]').inner_text()).strip()

                class_attr = await target.get_attribute("class") or ""
                if "is-soldout" in class_attr:
                    inventory_data[opt_name] = "품절"
                    slack_results.append(f"{opt_name} : 품절")
                    continue

                # 클릭 및 재고 확인 (이전 로직과 동일)
                await target.click(force=True)
                input_sel = 'input[data-qa-name="input-product-number"], input[class*="QuantityCounter_count"]'
                
                try:
                    await page.wait_for_selector(input_sel, timeout=5000)
                    input_field = page.locator(input_sel).first
                    await input_field.fill("999")
                    await page.keyboard.press("Enter")
                    
                    stock_text = "재고 확인 불가"
                    try:
                        toast_sel = 'div[class*="Toast_toast-inner"]'
                        await page.wait_for_selector(toast_sel, timeout=4000)
                        toast_content = await page.inner_text(toast_sel)
                        if "재고" in toast_content:
                            match = re.search(r'\d+', toast_content)
                            stock_text = f"재고 {match.group()}개"
                    except:
                        stock_text = "재고 999+ 예상"
                    
                    inventory_data[opt_name] = stock_text
                    slack_results.append(f"{opt_name} : {stock_text}")
                    
                    del_btn = page.locator('button[class*="OptionSelector_btn-delete"]').first
                    if await del_btn.is_visible():
                        await del_btn.click()
                        await asyncio.sleep(1.5)
                except:
                    inventory_data[opt_name] = "확인 불가"
                    slack_results.append(f"{opt_name} : 확인 불가")
                    await page.keyboard.press("Escape")

            # 🚀 재고 체크 종료 후 구글 시트 업데이트 호출
            update_google_sheet(inventory_data)
            return slack_results

        finally:
            await browser.close()

# ... (send_slack 함수는 기존과 동일)
