#!/usr/bin/env python
"""Test script to generate PDF and HTML without OpenStudio dependency."""

from pathlib import Path

print("Testing PDF and HTML generation...")

# Test PDF generation
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    
    output_dir = Path(__file__).parent / "tests" / "outputs"
    pdf_path = output_dir / "retrofit_analysis_report_test.pdf"
    
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    story.append(Paragraph("Test PDF Report", styles['Heading1']))
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("Energy Analysis", styles['Heading2']))
    story.append(Paragraph("Baseline: 450.50 GJ", styles['Normal']))
    story.append(Paragraph("Measure Applied: 380.25 GJ", styles['Normal']))
    story.append(Paragraph("Energy Savings: 70.25 GJ (15.6%)", styles['Normal']))
    
    doc.build(story)
    print(f"✓ PDF created: {pdf_path}")
    
except Exception as e:
    print(f"✗ PDF generation failed: {e}")
    import traceback
    traceback.print_exc()

# Test HTML generation
try:
    import plotly.graph_objects as go
    import pandas as pd
    
    output_dir = Path(__file__).parent / "tests" / "outputs"
    html_path = output_dir / "optimization_visualization_test.html"
    
    # Create sample data
    factors = ['Embodied Carbon', 'Embodied Energy', 'Cost', 'Air Quality', 'Water Impact']
    scenario_1 = [2/4, 3/10, 56/200, 36/40, 2/10]  # Normalized
    scenario_2 = [3/4, 2/10, 24/200, 25/40, 5/10]  # Normalized
    scenario_3 = [1/4, 6/10, 120/200, 30/40, 3/10]  # Normalized
    
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        theta=factors,
        r=scenario_1,
        name='Scenario_1',
        fill='toself'
    ))
    fig.add_trace(go.Scatterpolar(
        theta=factors,
        r=scenario_2,
        name='Scenario_2',
        fill='toself'
    ))
    fig.add_trace(go.Scatterpolar(
        theta=factors,
        r=scenario_3,
        name='Scenario_3',
        fill='toself'
    ))
    
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        showlegend=True,
        title="Retrofit Optimization Scenario Comparison"
    )
    
    fig.write_html(str(html_path))
    print(f"✓ HTML visualization created: {html_path}")
    
except Exception as e:
    print(f"✗ HTML generation failed: {e}")
    import traceback
    traceback.print_exc()

# Check files
output_dir = Path(__file__).parent / "tests" / "outputs"
if output_dir.exists():
    files = list(output_dir.glob("*"))
    print(f"\nFiles in {output_dir}:")
    for f in files:
        print(f"  - {f.name} ({f.stat().st_size} bytes)")
else:
    print(f"Output directory does not exist: {output_dir}")

print("\nTest complete!")
