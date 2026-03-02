import inquirer from 'inquirer';

export async function getPRNumber(): Promise<number> {
  const { prNumber } = await inquirer.prompt([
    {
      type: 'input',
      name: 'prNumber',
      message: 'Enter PR number to review:',
      validate: (input) => {
        const num = parseInt(input);
        return !isNaN(num) && num > 0 || 'Please enter a valid PR number';
      }
    }
  ]);

  return parseInt(prNumber);
}

export async function confirmContinue(message: string = 'Continue anyway?'): Promise<boolean> {
  const { confirmed } = await inquirer.prompt([
    {
      type: 'confirm',
      name: 'confirmed',
      message,
      default: false
    }
  ]);

  return confirmed;
}

export async function selectMigrationAction(): Promise<'view' | 'continue' | 'concern' | 'skip'> {
  const { action } = await inquirer.prompt([
    {
      type: 'list',
      name: 'action',
      message: 'How do you want to proceed?',
      choices: [
        { name: 'View full SQL', value: 'view' },
        { name: 'Continue to next', value: 'continue' },
        { name: 'Mark as concern', value: 'concern' },
        { name: 'Skip remaining migrations', value: 'skip' }
      ]
    }
  ]);

  return action;
}

export async function verifyRailwayDatabase(): Promise<{verified: boolean, restarted: boolean, migrationsChecked: boolean}> {
  const { verified } = await inquirer.prompt([
    {
      type: 'confirm',
      name: 'verified',
      message: 'Have you verified and updated DATABASE_URL in Railway?',
      default: false
    }
  ]);

  if (!verified) {
    return { verified: false, restarted: false, migrationsChecked: false };
  }

  const { restarted } = await inquirer.prompt([
    {
      type: 'confirm',
      name: 'restarted',
      message: 'Have you restarted the deployment after changing DATABASE_URL?',
      default: false
    }
  ]);

  const { migrationsChecked } = await inquirer.prompt([
    {
      type: 'confirm',
      name: 'migrationsChecked',
      message: 'Have you verified migrations ran successfully in deployment logs?',
      default: false
    }
  ]);

  return { verified, restarted, migrationsChecked };
}

export async function askToPostComment(): Promise<boolean> {
  const { shouldPost } = await inquirer.prompt([
    {
      type: 'confirm',
      name: 'shouldPost',
      message: 'Would you like to post this review as a comment on the PR?',
      default: true
    }
  ]);

  return shouldPost;
}
