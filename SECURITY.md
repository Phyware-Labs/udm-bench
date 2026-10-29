# Security policy

UDM-Bench is a research benchmark: it runs simulations locally and sends
telemetry to whatever model backend you configure. It runs no network service.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/Phyware-Labs/udm-bench/security/advisories/new),
not in a public issue.

Include what you found, how to reproduce it and the affected commit. You can
expect an acknowledgement within 5 working days and an assessment within 15.
Fixes land on `main`; there are no maintained release branches.

## Scope

In scope: code in this repository, for example the SQL guard in Condition B
(`harness/conditions/b_sql.py`), the bag and SQLite readers, and the
simulation images' build files.

Out of scope: the upstream ROS 2, Gazebo and PX4 software the images install,
and the behaviour of third-party model APIs.
