# TO-BE Design

The target process moves validation earlier and separates standard flow from exceptions.

## Key Changes

- Single digital request form for Sales and client-originated requests.
- Automatic mandatory-field validation.
- Pre-trade client and limit check before trader involvement.
- Single deal identifier from request creation to settlement.
- Automatic data transfer to trade capture after client acceptance.
- Standard deals follow an STP route.
- Exceptions are routed to a dedicated queue with owner, SLA and reason code.
- Confirmation is generated automatically from captured deal data.
- SLA timer sends alerts before breach.
- Every material change is written to audit log.

## Expected Effect

The target operating model does not remove Sales, Trader, Risk, Middle Office or Operations. It changes their focus: employees handle exceptions and controls, while standard deals move through the process with fewer manual handoffs.
