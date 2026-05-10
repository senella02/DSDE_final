import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import lib

from lib import clean_subset

PARTY_MAPPING = {
    "ก้าวไกล": "ประชาชน",
    "เพื่อไทย": "เพื่อไทย",
    "รวมไทยสร้างชาติ": "รวมไทยสร้างชาติ",
    "พลังประชารัฐ": "พลังประชารัฐ",
    "เป็นธรรม": "เป็นธรรม",
    "ท้องที่ไทย": "ท้องที่ไทย",
    "ภูมิใจไทย": "ภูมิใจไทย",
    "ประชาธิปัตย์": "ประชาธิปัตย์",
    "ใหม่": "ใหม่",
    "เพื่อชาติไทย": "เพื่อชาติไทย",
    "เสรีรวมไทย": "เสรีรวมไทย",
    "ชาติพัฒนากล้า": "ชาติพัฒนากล้า",
    "เพื่อชาติ": "เพื่อชาติ",
    "เพื่อไทรวมพลัง": "เพื่อไทรวมพลัง",
    "ไทยสร้างไทย": "ไทยสร้างไทย",
    "ไทยพร้อม": "ไทยพร้อม",
    "ประชากรไทย": "ประชากรไทย",
    "ทางเลือกใหม่": "ทางเลือกใหม่",
    "รวมใจไทย": "รวมใจไทย",
    "ประชาธิปไตยใหม่": "ประชาธิปไตยใหม่",
    "พลังสังคมใหม่": "พลังสังคมใหม่",
    "ไทยรวมไทย": "ไทยรวมไทย",
    "ไทยภักดี": "ไทยภักดี",
    "พลัง": "พลัง",
    "ชาติไทยพัฒนา": "ชาติไทยพัฒนา",
    "ภาคีเครือข่ายไทย": "ภาคีเครือข่ายไทย",
    "เปลี่ยน": "เปลี่ยน",
    "พลังเพื่อไทย": "พลังเพื่อไทย",
    "ประชาไทย": "ประชาไทย",
    "ครูไทยเพื่อประชาชน": "ครูไทยเพื่อประชาชน",
    "พลังธรรมใหม่": "พลังธรรมใหม่",
    "ไทยชนะ": "ไทยชนะ",
    "อนาคตไทย": "อนาคตไทย",
    "มิติใหม่": "มิติใหม่",
    "ไทยก้าวหน้า": "ไทยก้าวหน้า",
    "แรงงานสร้างชาติ": "แรงงานสร้างชาติ",
    "ประชาชาติ": "ประชาชาติ",
    "รวมพลัง": "รวมพลัง",
    "เปลี่ยนอนาคต": "เปลี่ยนอนาคต",
    "กรีน": "กรีน"
}

def plot_swing(df_2023, df_2026, party_colors, mode="district"):
    df_26_sub = df_2026[df_2026['ballot_type'] == mode].copy()
    
    if df_26_sub.empty:
        st.warning(f"⚠️ ไม่พบข้อมูลปี 2026 สำหรับประเภท: {mode}")
        return

    agg_dict_26 = {"votes": "sum"}
    has_name_26 = "name" in df_26_sub.columns and mode == "district"
    if has_name_26:
        agg_dict_26["name"] = "first"

    df_26_grouped = df_26_sub.groupby("party").agg(agg_dict_26).reset_index()
    cols_26 = ["party", "score_2026"]
    if has_name_26: cols_26.append("name_2026")
    df_26_grouped.columns = cols_26

    agg_dict_23 = {"score": "sum"}
    has_name_23 = "name" in df_2023.columns and mode == "district"
    if has_name_23:
        agg_dict_23["name"] = "first"

    df_23_grouped = df_2023.groupby("party").agg(agg_dict_23).reset_index()
    cols_23 = ["party", "score_2023"]
    if has_name_23: cols_23.append("name_2023")
    df_23_grouped.columns = cols_23

    df_compare = pd.merge(df_26_grouped, df_23_grouped, on="party", how="outer")
    
    df_compare['score_2026'] = df_compare['score_2026'].fillna(0).astype(float)
    df_compare['score_2023'] = df_compare['score_2023'].fillna(0).astype(float)
    df_compare['diff'] = df_compare['score_2026'] - df_compare['score_2023']
    
    df_compare = df_compare.sort_values(by="score_2026", ascending=False)

    max_parties = len(df_compare)
    
    st.subheader(f'เปรียบเทียบคะแนนระหว่างปี 2023 กับ 2026 - {mode.upper()}')
    
    col1, col2 = st.columns(2)
    
    with col1:
        top_n = st.slider(
            f"เลือกจำนวนพรรคที่ต้องการแสดง:", 
            min_value=1, 
            max_value=max_parties, 
            value=min(10, max_parties), 
            key=f"top_n_slider_{mode}" 
        )
    
    df_compare = df_compare.head(top_n)

    st.subheader(f"📋 ตารางข้อมูลเปรียบเทียบ ({mode.upper()}) - Top {top_n}")
    st.dataframe(
        df_compare.style.format({
            "score_2026": "{:,.0f}",
            "score_2023": "{:,.0f}",
            "diff": "{:+,.0f}"
        }),
        use_container_width=True
    )

    y_parties = df_compare['party'].astype(str).tolist()
    x_2023 = df_compare['score_2023'].tolist()
    x_2026 = df_compare['score_2026'].tolist()
    
    names_23 = df_compare['name_2023'].fillna("-").astype(str).tolist() if has_name_23 else ["-"] * len(df_compare)
    names_26 = df_compare['name_2026'].fillna("-").astype(str).tolist() if has_name_26 else ["-"] * len(df_compare)

    colors_26 = [party_colors.get(p, '#555555') if isinstance(party_colors, dict) else '#555555' for p in y_parties]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=y_parties, x=x_2023,
        name='ปี 2023', orientation='h', marker_color='#D3D3D3',
        customdata=names_23,
        hovertemplate="พรรค: %{y}<br>ผู้สมัคร: %{customdata}<br>คะแนน: %{x:,.0f}<extra></extra>"
    ))

    fig.add_trace(go.Bar(
        y=y_parties, x=x_2026,
        name='ปี 2026', orientation='h',
        marker_color=colors_26,
        customdata=names_26,
        hovertemplate="พรรค: %{y}<br>ผู้สมัคร: %{customdata}<br>คะแนน: %{x:,.0f}<extra></extra>"
    ))

    fig.update_layout(
        barmode='group',
        yaxis={'categoryorder':'total ascending'},
        height=max(400, top_n * 40) 
    )
    
    st.plotly_chart(fig, width="stretch")

def show_turnout_metrics(records, df_ballot_2023, mode):
    df_rec = records[records['ballot_type'] == mode].copy()
    
    col_mapping = {
        'eligible': 'eligible_voters', 
        'actual': 'voter_turnout', 
        'valid': 'valid_votes', 
        'invalid': 'void_ballots', 
        'novote': 'spoiled_ballots'
    }
    
    missing_cols = [col for col in col_mapping.values() if col not in df_rec.columns]
    if missing_cols:
        st.warning(f"⚠️ ไม่สามารถสร้างกราฟสถิติได้ เนื่องจากใน records.parquet ขาดคอลัมน์: {missing_cols}")
        return
    
    total_eligible_26 = df_rec[col_mapping['eligible']].sum()
    total_actual_26 = df_rec[col_mapping['actual']].sum()
    total_valid_26 = df_rec[col_mapping['valid']].sum()
    total_invalid_26 = df_rec[col_mapping['invalid']].sum()
    total_novote_26 = df_rec[col_mapping['novote']].sum()
    
    try:
        if 'ballot_type' in df_ballot_2023.columns:
            df_bal_23 = df_ballot_2023[df_ballot_2023['ballot_type'] == mode]
        else:
            df_bal_23 = df_ballot_2023

        total_eligible_23 = df_bal_23['eligible_voters'].sum() if 'eligible_voters' in df_bal_23.columns else 0
        total_actual_23 = df_bal_23['voter_turnout'].sum() if 'voter_turnout' in df_bal_23.columns else 0
        total_valid_23 = df_bal_23['valid_votes'].sum() if 'valid_votes' in df_bal_23.columns else 0
        total_invalid_23 = df_bal_23['void_ballots'].sum() if 'void_ballots' in df_bal_23.columns else 0
        total_novote_23 = df_bal_23['spoiled_ballots'].sum() if 'spoiled_ballots' in df_bal_23.columns else 0
    except Exception as e:
        st.warning(f"⚠️ รูปแบบไฟล์ json ของปี 2023 ไม่ตรงตามที่คาดหวัง: {e}")
        return
    
    def calc_pct(part, whole):
        return (part / whole * 100) if whole > 0 else 0

    pct_actual_23 = calc_pct(total_actual_23, total_eligible_23)
    pct_valid_23 = calc_pct(total_valid_23, total_actual_23)
    pct_invalid_23 = calc_pct(total_invalid_23, total_actual_23)
    pct_novote_23 = calc_pct(total_novote_23, total_actual_23)
    pct_actual_26 = calc_pct(total_actual_26, total_eligible_26)
    pct_valid_26 = calc_pct(total_valid_26, total_actual_26)
    pct_invalid_26 = calc_pct(total_invalid_26, total_actual_26)
    pct_novote_26 = calc_pct(total_novote_26, total_actual_26)


    st.subheader(f"สถิติการใช้สิทธิระหว่างปี 2023 กับ 2026 - {mode.upper()}")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        delta_actual = pct_actual_26 - pct_actual_23
        st.metric(label="👥 มาใช้สิทธิ (Turnout)", value=f"{pct_actual_26:.1f}%", delta=f"{delta_actual:+.1f}% เทียบปี 23")
        
    with col2:
        delta_valid = pct_valid_26 - pct_valid_23
        st.metric(label="✅ บัตรดี", value=f"{pct_valid_26:.1f}%", delta=f"{delta_valid:+.1f}%")
        
    with col3:
        delta_invalid = pct_invalid_26 - pct_invalid_23
        st.metric(label="❌ บัตรเสีย", value=f"{pct_invalid_26:.1f}%", delta=f"{delta_invalid:+.1f}%", delta_color="inverse")
        
    with col4:
        delta_novote = pct_novote_26 - pct_novote_23
        st.metric(label="🛑 งดออกเสียง", value=f"{pct_novote_26:.1f}%", delta=f"{delta_novote:+.1f}%", delta_color="inverse")

def debug_missing_turnout(records):
    st.subheader("🕵️‍♂️ ตรวจสอบความผิดปกติของข้อมูล Partylist (Turnout ต่ำ)")
    
    # 1. กรองเอาเฉพาะข้อมูล Partylist
    df_party = records[records['ballot_type'] == 'partylist'].copy()
    
    # ==========================================
    # 🆕 ส่วนที่เพิ่มใหม่: สรุปผลรวมของ Partylist ทั้งหมด
    # ==========================================
    st.markdown("**📊 ตารางสรุปผลรวม (Sum) ของข้อมูล Partylist ทั้งหมดในระบบ:**")
    cols_to_sum = ['eligible_voters', 'voter_turnout', 'valid_votes', 'void_ballots', 'spoiled_ballots']
    existing_cols = [c for c in cols_to_sum if c in df_party.columns]
    
    if existing_cols:
        # คำนวณผลรวม (ข้ามค่า Null ไป)
        sum_data = {col: df_party[col].sum(skipna=True) for col in existing_cols}
        df_sum = pd.DataFrame([sum_data])
        
        # แสดงเป็นตารางที่ใส่ลูกน้ำ (Comma) ให้ตัวเลขดูง่าย
        st.dataframe(df_sum.style.format("{:,.0f}"), use_container_width=True)
        
        # เช็ค% แบบเร็วๆ ให้ดูเลย
        if 'voter_turnout' in sum_data and 'eligible_voters' in sum_data and sum_data['eligible_voters'] > 0:
            raw_pct = (sum_data['voter_turnout'] / sum_data['eligible_voters']) * 100
            st.info(f"💡 คำนวณ Turnout จากผลรวมดิบ: ({sum_data['voter_turnout']:,.0f} / {sum_data['eligible_voters']:,.0f}) = **{raw_pct:.1f}%**")
    st.divider()
    # ==========================================

    # 2. หาแถวที่มีปัญหา (ผู้มีสิทธิ หรือ ผู้มาใช้สิทธิ เป็น 0 หรือค่าว่าง)
    mask_missing = (
        (df_party['eligible_voters'].isnull()) | (df_party['eligible_voters'] == 0) |
        (df_party['voter_turnout'].isnull()) | (df_party['voter_turnout'] == 0)
    )
    
    df_missing = df_party[mask_missing]
    
    # 3. แสดงผลเป็นตาราง
    if df_missing.empty:
        st.success("✅ ไม่พบแถวที่ค่า voter_turnout หรือ eligible_voters เป็น 0 (ปัญหาเกิดจากข้อมูลที่สกัดมาได้มีจำนวนแถวน้อยกว่า District)")
        
        # ลองเทียบจำนวนแถวดู
        count_district = len(records[records['ballot_type'] == 'district'])
        count_party = len(df_party)
        st.info(f"📋 เปรียบเทียบจำนวนข้อมูล (Rows): District = **{count_district} แถว** | Partylist = **{count_party} แถว**")
        
    else:
        st.warning(f"⚠️ พบข้อมูลที่ยอดผู้ใช้สิทธิหายไป (voter_turnout/eligible_voters = 0 หรือค่าว่าง) จำนวน **{len(df_missing)} แถว** จากทั้งหมด {len(df_party)} แถว")
        
        # ดึงคอลัมน์ที่จำเป็นมาแสดง
        cols_to_show = [c for c in records.columns if c not in ['created_at', 'updated_at']]
        st.dataframe(df_missing[cols_to_show], use_container_width=True)

def render(records, candidates, pages, official):
    # Load data from 2023
    df_district_2023 = pd.read_csv("data/korat2023_data/district_2023.csv")
    df_partylist_2023 = pd.read_csv("data/korat2023_data/partylist_2023.csv")
    df_ballot_2023 = pd.read_json("data/korat2023_data/ballot_count.json")
    
    df_district_2023['party'] = df_district_2023['party'].map(PARTY_MAPPING).fillna(df_district_2023['party'])
    df_partylist_2023['party'] = df_partylist_2023['party'].map(PARTY_MAPPING).fillna(df_partylist_2023['party'])
    
    is_outlier = (candidates['party'] == 'เพื่อชาติไทย') & \
                 (candidates['ballot_type'] == 'partylist') & \
                 (candidates['count_tier'] == 'B')
    
    candidates = candidates[~is_outlier]

    df_2026, caption = clean_subset(candidates, count_tier=["A", "B", "C"])
    st.info(f"💡 {caption}")
    
    view_mode = st.radio(
        "ประเภทการวิเคราะห์:", 
        ["District", "Partylist"], 
        horizontal=True,
        key="mode_swing_selector"
    )
    df_old = df_partylist_2023
    if view_mode == "District":
        df_old = df_district_2023
        
    show_turnout_metrics(records, df_ballot_2023, mode=view_mode.lower())
    st.space(12)
    plot_swing(df_old, df_2026, lib.PALETTE, mode=view_mode.lower())
    
    with st.expander("🔗 แหล่งที่มาของข้อมูลปี 2023 (Data Sources)"):
        st.write("ข้อมูลเปรียบเทียบผลการเลือกตั้งปี 2566 รวบรวมและอ้างอิงจาก:")
        col_ref1, col_ref2 = st.columns(2)
        with col_ref1:
            st.markdown("- [Voice TV - Vote 66](https://vote66.voicetv.co.th/)")
            st.markdown("- [WorkpointToday - Vote 66](https://vote66.workpointtoday.com/)")
        with col_ref2:
            st.markdown("- [The Standard - Election 2566](https://election2566.thestandard.co/)")
            st.markdown("- [Wikipedia - การเลือกตั้ง นครราชสีมา เขต 5 (2566)](https://th.wikipedia.org/wiki/%E0%B8%88%E0%B8%B1%E0%B8%87%E0%B8%AB%E0%B8%A7%E0%B8%B1%E0%B8%94%E0%B8%99%E0%B8%84%E0%B8%A3%E0%B8%A3%E0%B8%B2%E0%B8%8A%E0%B8%AA%E0%B8%B5%E0%B8%A1%E0%B8%B2%E0%B9%83%E0%B8%99%E0%B8%81%E0%B8%B2%E0%B8%A3%E0%B9%80%E0%B8%A5%E0%B8%B7%E0%B8%AD%E0%B8%81%E0%B8%95%E0%B8%B1%E0%B9%89%E0%B8%87%E0%B8%AA%E0%B8%A1%E0%B8%B2%E0%B8%8A%E0%B8%B4%E0%B8%81%E0%B8%AA%E0%B8%A0%E0%B8%B2%E0%B8%9C%E0%B8%B9%E0%B9%89%E0%B9%81%E0%B8%97%E0%B8%99%E0%B8%A3%E0%B8%B2%E0%B8%A9%E0%B8%8E%E0%B8%A3%E0%B9%84%E0%B8%97%E0%B8%A2%E0%B9%80%E0%B8%9B%E0%B9%87%E0%B8%99%E0%B8%81%E0%B8%B2%E0%B8%A3%E0%B8%97%E0%B8%B1%E0%B9%88%E0%B8%A7%E0%B9%84%E0%B8%9B_%E0%B8%9E.%E0%B8%A8._2566#%E0%B9%80%E0%B8%82%E0%B8%95_5)")
            
    with st.expander("🔍 ดูข้อมูลดิบที่มีปัญหา (Debug)"):
        debug_missing_turnout(records)
