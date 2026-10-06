category: security
# Roles and least privilege
Use separate roles for the application, migrations, and administration. The application role gets only the table privileges it needs, such as SELECT, INSERT, UPDATE and DELETE. Never connect an application as a superuser. Store passwords in a secrets manager and rotate them.
