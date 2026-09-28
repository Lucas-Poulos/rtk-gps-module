# Not-fitted parts

Footprints deliberately left unpopulated. Each is a documented
option, not an omission -- fitting one changes a behaviour the
default build does not want.

| Ref | Value | Pkg | Why it exists |
|---|---|---|---|
| `C302` | DNP | C_0402_1005Metric | pi-match shunt, antenna side -- fit only if the antenna needs it |
| `C303` | DNP | C_0402_1005Metric | pi-match shunt, filter side -- fit only if the antenna needs it |
| `R206` | 0R | R_0402_1005Metric | pull D_SEL1 high to select SPI/I2C instead of UART1 |
| `R207` | 0R | R_0402_1005Metric | pull D_SEL2 high to select I2C instead of UART1 |
| `R208` | 0R | R_0402_1005Metric | brings I2C_SDA out to the castellated edge |
| `R209` | 0R | R_0402_1005Metric | brings I2C_SCL out to the castellated edge |
| `R210` | 0R | R_0402_1005Metric | brings TXD2 (1.8 V debug UART) out to the castellated edge |
| `R211` | 0R | R_0402_1005Metric | brings RXD2 (1.8 V debug UART) out to the castellated edge |
| `R305` | 0R | R_0402_1005Metric | bypasses the ANT_ON switch to power the antenna unconditionally |
