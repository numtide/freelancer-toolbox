# Germany

Welcome to the world's most complex tax system!

## Tax Registration

### Becoming Self-Employed

1. **Sign up for ELSTER** - The electronic system for submitting taxes and forms. Highly recommended as it provides form validation and hints.

2. **Fill out "Fragebogen zur steuerlichen Erfassung"** - This declares your business. Use this guide: <https://allaboutberlin.com/guides/fragebogen-zur-steuerlichen-erfassung>

   Key choices:
   - **Business type:** Freiberufler (recommended for IT/consulting)
   - **Gewinnermittlungsart (profit assessment):** Einnahmen-Überschuss-Rechnung (simpler than double-entry accounting)
   - **Soll-/Istversteuerung (VAT payment method):** Istversteuerung - you only pay VAT once you receive payment (protects against non-paying clients)

### VAT Number (Umsatzsteuernummer)

Use this number on invoices so clients in other countries can verify VAT status. While you can use your "Steuernummer," the VAT number is safer to share publicly. Many foreign companies only waive VAT if you provide a VAT number.

Apply here: <https://www.bzst.de/DE/Unternehmen/Identifikationsnummern/Umsatzsteuer-Identifikationsnummer/Vergabe_USt_IdNr/vergabe_ust_idnr_node.html#js-toc-entry2>

**Tip:** The letter can take weeks, but you can often call them to get your number earlier since it's usually allocated before they mail it.

### Statusfeststellungsverfahren

This pension system check determines if you're an employee or self-employed. Unless requested by a client, you probably don't need to initiate it. Instead, follow best practices to clearly appear as an independent business (own website, multiple clients, own branding, etc.).

See: [Statusfeststellungsverfahren Guide (PDF)](./germany/01_Steimke-Registermodernisierung.pdf)

For German speakers, this podcast gives a nice overview: <https://steuer-podcast.podigee.io/>

## Health Insurance

If you're still employed while being self-employed, you need to determine your main source of income to decide whether to pay health insurance yourself. Contact your health insurance provider to arrange this.

If you don't have health insurance, [TK (Techniker Krankenkasse)](https://tk.de) is a solid choice. They offer professional support in English and are generally straightforward to work with.

### GKV vs Private Insurance

In Germany, you can choose between private insurance and "freiwillig gesetzlich versichert" (GKV). Your private insurance cost depends on your health and other factors. GKV is based on your income (see [TK's contribution calculator](https://www.tk.de/techniker/leistungen-und-mitgliedschaft/informationen-versicherte/veraenderung-berufliche-situation/freiwillige-krankenversicherung-tk/haeufige-fragen-zu-beitraegen-fuer-freiwillig-versicherte/beitragshoehe-arbeitnehmer-2006954?tkcm=ab)).

As a freelancer in IT, you'll likely pay the maximum monthly fee (capped at 4,987.50 EUR income per month as of 2023). While private insurance may seem cheaper for young/healthy people with additional services, consider:

- Private fees increase with age while income often drops. GKV fees decrease when income drops.
- You can switch from GKV to private, but can only switch back if you're under 55 and earn less than 66,600 EUR/year.
- For families: the higher-earning partner must insure children. Private insurance charges extra per child; GKV does not.

**Recommendation:** Go with GKV (public health insurance).

## Accounting Software

[SevDesk](https://sevdesk.com) works well for German freelancers:
- Usable interface
- Good at parsing PDF invoices
- Can submit VAT reports directly to the tax office (Umsatzsteuervoranmeldung)
- API available for automation

In Germany, have your health insurance charge from your business account since it's a tax-relevant expense.

## Toolbox Integration

This toolbox provides several tools specifically useful for German freelancers:

| Tool | Description |
|------|-------------|
| **[sevdesk-cli](../../sevdesk-cli/)** | Manage vouchers, tax rules, and accounting |
| **[sevdesk-invoicer](../../sevdesk-invoicer/)** | Generate invoices from time tracking data |
| **[sevdesk-tax-estimator](../../sevdesk-invoicer/)** | Calculate remaining income tax payments |
| **[sevdesk-wise-importer](../../sevdesk-invoicer/)** | Import Wise bank transactions |

### Tax Estimation Workflow

Calculate how much tax you still owe for the year:

```console
sevdesk-tax-estimator \
  --harvest-folder harvest/2024 \
  --wise-folder statements/2024 \
  --tax-office-name "Finanzamt Berlin Finanzkasse"
```

Use the [BMF Tax Calculator](https://www.bmf-steuerrechner.de/) to calculate your income tax based on net income.

### Working Days for Tax Deductions

For income tax, you can claim deductions per working day (Entfernungspauschale, home office). Calculate from your Harvest time report:

```console
working-days-calculator report.csv
```

---

[Back to Countries](./README.md) | [Getting Started](../getting-started.md)
