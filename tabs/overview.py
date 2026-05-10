import streamlit as st
import plotly.graph_objects as go
import lib 
import pandas as pd

from lib import clean_subset

def plot_split_ticket(df_candidates, party_colors):
    df_grouped =  df_candidates.groupby(['party', 'ballot_type'])['votes'].sum().reset_index()
    
    df_pivot = pd.pivot_table(
        df_grouped,
        index='party',
        columns='ballot_type',
        values='votes',
        aggfunc='sum'
    ).fillna(0).reset_index()
    
    for col in ['district', 'partylist']:
        if col not in df_pivot.columns:
            df_pivot[col] = 0
    
    df_pivot['total_votes'] = df_pivot['district'] + df_pivot['partylist']
    df_pivot['gap'] = df_pivot['district'] - df_pivot['partylist']
    
    df_pivot = df_pivot.sort_values(by='total_votes', ascending=False)
    
    max_parties = len(df_pivot)
    if max_parties == 0:
        st.warning("⚠️ ไม่พบข้อมูลสำหรับสร้างกราฟ Split-ticket")
        return
    
    st.subheader(f"เปรียบเทียบคะแนน สส.เขต (District) vs สส.บัญชีรายชื่อ (Partylist)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        top_n = st.slider(
            f"เลือกจำนวนพรรคที่ต้องการแสดง:", 
            min_value=1, 
            max_value=max_parties, 
            value=min(10, max_parties), 
            key="split_ticket_top_n_slider" 
        )
    with col2:
        value_type = st.selectbox(
            "เลือกประเภทการข้อมูล",
            ("ส่วนต่างคะแนน (Gap)", "เปรียบเทียบคะแนนดิบ")
        )
    
    df_top = df_pivot.head(top_n).sort_values(by='total_votes', ascending=True)
    
    # st.caption("**Gap เป็นบวก (+)**: คนเลือก ส.ส.เขต มากกว่าพรรค | **Gap เป็นลบ (-)**: คนเลือกพรรค มากกว่า ส.ส.เขต")
    
    # df_table = df_top.sort_values(by='total_votes', ascending=False)
    # st.dataframe(
    #     df_table[['party', 'district', 'partylist', 'gap', 'total_votes']].style.format({
    #         "district": "{:,.0f}",
    #         "partylist": "{:,.0f}",
    #         "gap": "{:+,.0f}",
    #         "total_votes": "{:,.0f}"
    #     }),
    #     use_container_width=True
    # )

    # tab_gap, tab_compare = st.tabs(["ส่วนต่างคะแนน (Gap)", "เปรียบเทียบคะแนนดิบ"])

    if value_type == 'ส่วนต่างคะแนน (Gap)':
        fig_gap = go.Figure()
        
        fig_gap.add_trace(go.Bar(
            y=df_top['party'], 
            x=df_top['gap'],
            orientation='h',
            marker_color=[party_colors.get(p, '#555555') for p in df_top['party']],
            text=df_top['gap'].apply(lambda x: f"{x:+,.0f}"),
            textposition="auto",
            hovertemplate="พรรค: %{y}<br>ส่วนต่าง (Gap): %{x:+,.0f}<extra></extra>"
        ))
        
        fig_gap.update_layout(
            title="ส่วนต่างคะแนน (สส.เขต - สส.บัญชีรายชื่อ)",
            xaxis_title="← พรรคแบกคน (บัญชีรายชื่อเยอะกว่า)  |  คนแบกพรรค (เขตเยอะกว่า) →",
            height=max(400, top_n * 40),
            xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor='black') # เส้นแกนกลาง 0
        )
        st.plotly_chart(fig_gap, width='stretch')

    if value_type == 'เปรียบเทียบคะแนนดิบ':
        fig_comp = go.Figure()

        fig_comp.add_trace(go.Bar(
            y=df_top['party'], x=df_top['district'],
            name='สส.เขต (เลือกคน)', orientation='h',
            marker_color=[party_colors.get(p, '#555555') for p in df_top['party']],
            hovertemplate="พรรค: %{y}<br>คะแนนเขต: %{x:,.0f}<extra></extra>"
        ))

        fig_comp.add_trace(go.Bar(
            y=df_top['party'], x=df_top['partylist'],
            name='สส.บัญชีรายชื่อ (เลือกพรรค)', orientation='h',
            marker_color=[party_colors.get(p, '#555555') for p in df_top['party']],
            marker=dict(opacity=0.5, pattern_shape="/"), # ทำให้โปร่งใส และใส่ลายขีดๆ
            hovertemplate="พรรค: %{y}<br>คะแนนพรรค: %{x:,.0f}<extra></extra>"
        ))

        fig_comp.update_layout(
            barmode='group',
            title='เปรียบเทียบคะแนนโหวตรายพรรค (บัตร 2 ใบ)',
            height=max(400, top_n * 50),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_comp, width='stretch')
    
def plot_advance_vs_election_day(df_advance, df_election, party_colors):
    
    df_adv_grp = df_advance.groupby('party')['votes'].sum().reset_index()
    total_adv = df_adv_grp['votes'].sum()
    df_adv_grp['pct_advance'] = (df_adv_grp['votes'] / total_adv) * 100

    df_elec_grp = df_election.groupby('party')['votes'].sum().reset_index()
    total_elec = df_elec_grp['votes'].sum()
    df_elec_grp['pct_regular'] = (df_elec_grp['votes'] / total_elec) * 100

    df_compare = pd.merge(
        df_adv_grp[['party', 'pct_advance', 'votes']], 
        df_elec_grp[['party', 'pct_regular', 'votes']], 
        on='party', how='outer', suffixes=('_adv', '_reg')
    ).fillna(0)
    
    col1, col2 = st.columns(2)
    with col1:
        max_parties = len(df_compare)
        top_n = st.slider(
            "เลือกจำนวนพรรคที่ต้องการแสดง (Advance vs Regular):", 
            min_value=1, max_value=max_parties, value=min(10, max_parties),
            key="advance_top_n_slider"
        )
    with col2:
        compare_type = st.selectbox(
            'เลือกประเภทการเปรียบเทียบ:',
            ("ส่วนต่างสัดส่วน (% Gap)", "เทียบเปอร์เซ็นต์โดยตรง")
        )

    df_compare['gap_pct'] = df_compare['pct_advance'] - df_compare['pct_regular']
    df_compare['total_votes_both'] = df_compare['votes_adv'] + df_compare['votes_reg']
    df_compare = df_compare.sort_values(by='total_votes_both', ascending=False)
    df_top = df_compare.head(top_n).sort_values(by='total_votes_both', ascending=True)
    
    st.caption(f"จำนวนผู้ใช้สิทธิล่วงหน้าที่นับได้: **{total_adv:,.0f}** เสียง | วันจริง: **{total_elec:,.0f}** เสียง (แปลงเป็น % เพื่อให้เทียบกันได้)")
    
    if compare_type == 'ส่วนต่างสัดส่วน (% Gap)':
        fig_gap = go.Figure()
        
        fig_gap.add_trace(go.Bar(
            y=df_top['party'], 
            x=df_top['gap_pct'],
            orientation='h',
            marker_color=[party_colors.get(p, '#555555') for p in df_top['party']],
            text=df_top['gap_pct'].apply(lambda x: f"{x:+,.1f}%"),
            textposition="auto",
            hovertemplate="พรรค: %{y}<br>ส่วนต่าง: %{x:+,.2f}%<extra></extra>"
        ))
        
        fig_gap.update_layout(
            title="ส่วนต่างสัดส่วน (% ล่วงหน้า - % วันจริง)",
            xaxis_title="← คนในพื้นที่ชอบมากกว่า (วันจริง % สูงกว่า)  |  คนต่างถิ่นชอบมากกว่า (ล่วงหน้า % สูงกว่า) →",
            height=max(400, top_n * 40),
            xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor='black')
        )
        st.plotly_chart(fig_gap, width='stretch')

    if compare_type == 'เทียบเปอร์เซ็นต์โดยตรง':
        fig_comp = go.Figure()

        fig_comp.add_trace(go.Bar(
            y=df_top['party'], x=df_top['pct_advance'],
            name='เลือกล่วงหน้า (%)', orientation='h',
            marker_color=[party_colors.get(p, '#555555') for p in df_top['party']],
            hovertemplate="พรรค: %{y}<br>ล่วงหน้า: %{x:.2f}%<extra></extra>"
        ))

        fig_comp.add_trace(go.Bar(
            y=df_top['party'], x=df_top['pct_regular'],
            name='เลือกวันจริง (%)', orientation='h',
            marker_color=[party_colors.get(p, '#555555') for p in df_top['party']],
            marker=dict(opacity=0.5, pattern_shape="x"), # ทำลายแพทเทิร์นให้ต่างกัน
            hovertemplate="พรรค: %{y}<br>วันจริง: %{x:.2f}%<extra></extra>"
        ))

        fig_comp.update_layout(
            barmode='group',
            title='เปรียบเทียบสัดส่วนคะแนน (%)',
            xaxis_title="สัดส่วนคะแนนเสียง (%)",
            height=max(400, top_n * 50),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_comp, width='stretch')

def show_executive_summary_table(df_candidates):
    st.subheader("📋 ตารางสรุปพฤติกรรมการโหวตรายพรรค (Executive Summary)")
    
    df_grouped = df_candidates.groupby(['party', 'ballot_type'])['votes'].sum().reset_index()
    df_pivot = pd.pivot_table(
        df_grouped, index='party', columns='ballot_type', values='votes', aggfunc='sum'
    ).fillna(0).reset_index()
    
    for col in ['district', 'partylist']:
        if col not in df_pivot.columns: df_pivot[col] = 0

    df_pivot['total'] = df_pivot['district'] + df_pivot['partylist']
    df_pivot['gap'] = df_pivot['district'] - df_pivot['partylist']
    
    def analyze_behavior(gap, total):
        if total == 0: return "ไม่มีข้อมูล"
        pct_diff = abs(gap) / total
        if pct_diff < 0.05:
            return "⚖️ เลือกพรรคเดียวทั้งสองใบ (Straight-Ticket)"
        elif gap > 0:
            return "👤 นิยมตัวบุคคล (Candidate-Centric)"
        else:
            return "🚩 นิยมพรรค (Party-Centric)"

    df_pivot['behavior'] = df_pivot.apply(lambda row: analyze_behavior(row['gap'], row['total']), axis=1)
    
    col1, col2 = st.columns(2)
    
    with col1:
        behavior_options = [
            "แสดงทั้งหมด", 
            "⚖️ เลือกพรรคเดียวทั้งสองใบ (Straight-Ticket)", 
            "👤 นิยมตัวบุคคล (Candidate-Centric)", 
            "🚩 นิยมพรรค (Party-Centric)"
        ]
        selected_behavior = st.selectbox("กรองตามพฤติกรรมการลงคะแนน:", behavior_options)
        
    with col2:
        all_parties = sorted(df_pivot['party'].unique().tolist())
        selected_parties = st.multiselect("ค้นหาพรรคการเมือง:", all_parties)

    df_filtered = df_pivot.copy()
    
    if selected_behavior != "แสดงทั้งหมด":
        df_filtered = df_filtered[df_filtered['behavior'] == selected_behavior]
        
    if selected_parties:
        df_filtered = df_filtered[df_filtered['party'].isin(selected_parties)]

    df_filtered = df_filtered.sort_values(by='total', ascending=False)
    
    df_show = df_filtered[['party', 'district', 'partylist', 'behavior']].copy()
    df_show.columns = ['พรรคการเมือง', 'คะแนน สส.เขต', 'คะแนน สส.บัญชีรายชื่อ', 'วิเคราะห์รูปแบบการโหวต']
    
    if df_show.empty:
        st.warning("❌ ไม่พบข้อมูลที่ตรงตามเงื่อนไข")
    else:
        st.dataframe(
            df_show.style.format({
                "คะแนน สส.เขต": "{:,.0f}",
                "คะแนน สส.บัญชีรายชื่อ": "{:,.0f}"
            }),
            use_container_width=True,
            hide_index=True
        )
        
        st.caption(f"แสดงข้อมูลทั้งหมด {len(df_show)} พรรค")


def render(records: pd.DataFrame, candidates: pd.DataFrame, pages: pd.DataFrame, official: pd.DataFrame) -> None:
    df_2026, caption = clean_subset(candidates, count_tier=["A", "B", "C"])
    st.info(f"💡 {caption}")
    
    plot_split_ticket(df_2026, lib.PALETTE)
    st.write('---')
    
    st.markdown("### เปรียบเทียบสัดส่วนคะแนนเสียง: ล่วงหน้า vs วันจริง")
    
    view_mode = st.radio(
        "ประเภทการวิเคราะห์", 
        ["District", "Partylist"], 
        horizontal=False,
        key="mode_overview_selector"
    )
        
    df_curr = df_2026[df_2026['ballot_type'] == view_mode.lower()]
    df_adv = df_curr[df_curr['election_type'].str.contains('advance')]
    df_reg = df_curr[df_curr['election_type'] == 'normal']
    plot_advance_vs_election_day(df_adv, df_reg, lib.PALETTE)
    st.write('---')
    
    show_executive_summary_table(df_2026)
